"""
File upload and Google Docs creation logic for Google Drive sync.

Provides mixin class with methods for uploading markdown, CSV, and
PDF files to Google Drive/Docs with embedded content support.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from ..converter import CSVConverter, MarkdownConverter, PDFConverter

logger = logging.getLogger(__name__)


class UploaderMixin:
    """Mixin providing file upload methods for GoogleDriveSync.

    Contains the main ``markdown_to_doc_with_diagrams`` workflow that
    converts markdown files to Google Docs with embedded content.

    Expects the host class to provide:
    - ``self.service``: Google Drive API service (for file operations)
    - ``self.folder_id``: Default Google Drive folder ID
    - ``self.use_cache``: Whether caching is enabled
    - ``self.cache``: SyncCache instance
    - ``self.enable_mermaid``: Whether Mermaid processing is enabled
    - ``self.gdocs_service``: GoogleDocsService instance
    - ``self.gdrive_service``: GoogleDriveService instance
    - ``self._execute_with_retry(request)``: Retry-enabled API execution
    - ``self._process_mermaid_diagrams(doc_id, diagrams, folder_id)``
    - ``self._process_ascii_codeblocks(doc_id, blocks, folder_id)``
    - ``self._process_code_blocks(doc_id, blocks, folder_id)``
    - ``self._process_local_images(doc_id, images, folder_id)``
    """

    def markdown_to_doc_with_diagrams(
        self,
        md_file: Path,
        folder_id: str | None = None,
        custom_name: str | None = None,
        enable_images: bool = True
    ) -> str:
        """Convert markdown file to Google Docs with Mermaid diagram and image support.

        Workflow:
        1. Extract Mermaid diagrams from markdown
        2. Extract local image references from markdown
        3. Upload markdown with markers to Google Docs
        4. Render Mermaid diagrams as PNG images
        5. Upload local images to Google Drive
        6. Embed all images at marker positions

        Args:
            md_file: Path to markdown file.
            folder_id: Target Google Drive folder ID.
            custom_name: Optional custom name for the document.
            enable_images: Whether to embed local images (default: True).

        Returns:
            Google Doc ID.
        """
        md_file = Path(md_file)
        folder_id = folder_id or self.folder_id or 'root'

        # Check cache
        if self.use_cache:
            should_sync, reason = self.cache.should_sync(md_file)
            if not should_sync:
                logger.info(f"Skipped: {md_file} ({reason})")
                return self.cache.cache[str(md_file)].get('drive_id')
            logger.info(f"Syncing: {md_file} ({reason})")
        else:
            logger.info(f"Syncing: {md_file}")

        # Prepare markdown with diagram and image extraction
        converter = MarkdownConverter()
        file_metadata = converter.prepare_for_upload(
            md_file,
            format_code=True,
            extract_diagrams=self.enable_mermaid,
            extract_images=enable_images
        )

        if custom_name:
            file_metadata['name'] = custom_name

        file_name = file_metadata['name']
        temp_file = file_metadata.get('temp_file')
        diagrams = file_metadata.get('diagrams', [])
        images = file_metadata.get('images', [])
        ascii_blocks = file_metadata.get('ascii_blocks', [])
        code_blocks = file_metadata.get('code_blocks', [])

        try:
            # Check if document already exists
            query = (
                f"name='{file_name}' and mimeType='application/vnd.google-apps.document' "
                f"and '{folder_id}' in parents and trashed=false"
            )
            request = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name)',
                supportsAllDrives=True,
                includeItemsFromAllDrives=True
            )
            results = self._execute_with_retry(request)
            files = results.get('files', [])

            # Upload markdown to Google Docs
            upload_file = temp_file if temp_file else str(md_file)
            media = MediaFileUpload(upload_file, mimetype='text/markdown', resumable=True)

            if files:
                # Update existing document
                request = self.service.files().update(
                    fileId=files[0]['id'],
                    media_body=media,
                    supportsAllDrives=True
                )
                doc = self._execute_with_retry(request)
                logger.info(f"Updated: {md_file} -> Google Doc")
                doc_id = doc['id']
            else:
                # Create new document
                file_metadata['mimeType'] = 'application/vnd.google-apps.document'
                file_metadata['parents'] = [folder_id]

                request = self.service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id',
                    supportsAllDrives=True
                )
                doc = self._execute_with_retry(request)
                logger.info(f"Created: {md_file} -> Google Doc")
                doc_id = doc['id']

            # Process Mermaid diagrams if any
            if self.enable_mermaid and diagrams and self.gdocs_service and self.gdrive_service:
                logger.info(f"Processing {len(diagrams)} Mermaid diagrams...")
                self._process_mermaid_diagrams(doc_id, diagrams, folder_id)

            # Process ASCII code blocks (wireframes) if any
            if ascii_blocks and self.gdocs_service and self.gdrive_service:
                logger.info(f"Processing {len(ascii_blocks)} ASCII wireframes...")
                self._process_ascii_codeblocks(doc_id, ascii_blocks, folder_id)

            # Process syntax-highlighted code blocks if any
            if code_blocks and self.gdocs_service and self.gdrive_service:
                logger.info(f"Processing {len(code_blocks)} code blocks...")
                self._process_code_blocks(doc_id, code_blocks, folder_id)

            # Process local images if any
            if enable_images and images and self.gdocs_service and self.gdrive_service:
                logger.info(f"Processing {len(images)} local images...")
                self._process_local_images(doc_id, images, folder_id)

            # Process anchor links if enabled
            enable_anchor_links = os.getenv('ENABLE_ANCHOR_LINKS', 'true').lower() == 'true'
            if enable_anchor_links and self.gdocs_service:
                try:
                    converted_count = self.gdocs_service.process_anchor_links(doc_id)
                    if converted_count > 0:
                        logger.info(f"Converted {converted_count} anchor links")
                except Exception as e:
                    # Don't fail entire sync if anchor conversion fails
                    logger.warning(f"Failed to convert anchor links: {e}")

            # Update cache
            if self.use_cache:
                self.cache.update(md_file, doc_id)

            # Clean up temp file
            if temp_file and os.path.exists(temp_file):
                os.unlink(temp_file)

            return doc_id

        except Exception as error:
            # Clean up temp file on error
            if temp_file and os.path.exists(temp_file):
                os.unlink(temp_file)
            raise Exception(f"Error syncing {md_file}: {error}") from error

    def csv_to_sheet(self, csv_file: Path, folder_id: str | None = None, custom_name: str | None = None) -> str:
        """Convert and upload CSV file to Google Sheets.

        Args:
            csv_file: Path to CSV file.
            folder_id: Target Google Drive folder ID.
            custom_name: Optional custom name for the spreadsheet.

        Returns:
            Google Sheets file ID.
        """
        csv_file = Path(csv_file)
        folder_id = folder_id or self.folder_id or 'root'

        converter = CSVConverter()
        file_metadata = converter.prepare_for_upload(csv_file)

        if custom_name:
            file_metadata['name'] = custom_name

        file_name = file_metadata['name']

        try:
            query = (
                f"name='{file_name}' and mimeType='application/vnd.google-apps.spreadsheet' "
                f"and '{folder_id}' in parents and trashed=false"
            )
            request = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name, webViewLink)',
                supportsAllDrives=True,
                includeItemsFromAllDrives=True
            )
            results = self._execute_with_retry(request)

            files = results.get('files', [])
            media = MediaFileUpload(str(csv_file), mimetype='text/csv', resumable=True)

            if files:
                request = self.service.files().update(
                    fileId=files[0]['id'],
                    media_body=media,
                    fields='id,webViewLink',
                    supportsAllDrives=True
                )
                sheet = self._execute_with_retry(request)
                logger.info(f"Updated: {csv_file} -> Google Sheet")
                logger.info(f"   View at: {sheet.get('webViewLink')}")
            else:
                file_metadata['mimeType'] = converter.get_conversion_mimetype()
                file_metadata['parents'] = [folder_id]

                request = self.service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id,webViewLink',
                    supportsAllDrives=True
                )
                sheet = self._execute_with_retry(request)
                logger.info(f"Created: {csv_file} -> Google Sheet")
                logger.info(f"   View at: {sheet.get('webViewLink')}")

            return sheet['id']

        except HttpError as error:
            raise Exception(f"Error syncing {csv_file}: {error}") from error

    def pdf_to_drive(self, pdf_file: Path, folder_id: str | None = None, custom_name: str | None = None) -> str:
        """Upload PDF file directly to Google Drive (no conversion).

        Args:
            pdf_file: Path to PDF file.
            folder_id: Target Google Drive folder ID.
            custom_name: Optional custom name for the file.

        Returns:
            Google Drive file ID.
        """
        pdf_file = Path(pdf_file)
        folder_id = folder_id or self.folder_id or 'root'

        converter = PDFConverter()
        file_metadata = converter.prepare_for_upload(pdf_file)

        if custom_name:
            file_metadata['name'] = custom_name

        file_name = file_metadata['name']

        # Check cache
        if self.use_cache:
            should_sync, reason = self.cache.should_sync(pdf_file)
            if not should_sync:
                logger.info(f"Skipped: {pdf_file} ({reason})")
                return self.cache.cache[str(pdf_file)].get('drive_id')
            logger.info(f"Syncing: {pdf_file} ({reason})")
        else:
            logger.info(f"Syncing: {pdf_file}")

        try:
            query = (
                f"name='{file_name}' and mimeType='application/pdf' "
                f"and '{folder_id}' in parents and trashed=false"
            )
            request = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name, webViewLink)',
                supportsAllDrives=True,
                includeItemsFromAllDrives=True
            )
            results = self._execute_with_retry(request)

            files = results.get('files', [])
            media = MediaFileUpload(str(pdf_file), mimetype='application/pdf', resumable=True)

            if files:
                request = self.service.files().update(
                    fileId=files[0]['id'],
                    media_body=media,
                    fields='id,webViewLink',
                    supportsAllDrives=True
                )
                pdf = self._execute_with_retry(request)
                logger.info(f"Updated: {pdf_file} -> Google Drive PDF")
                logger.info(f"   View at: {pdf.get('webViewLink')}")
            else:
                file_metadata['parents'] = [folder_id]

                request = self.service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id,webViewLink',
                    supportsAllDrives=True
                )
                pdf = self._execute_with_retry(request)
                logger.info(f"Created: {pdf_file} -> Google Drive PDF")
                logger.info(f"   View at: {pdf.get('webViewLink')}")

            # Update cache
            if self.use_cache:
                self.cache.update(pdf_file, pdf['id'])

            return pdf['id']

        except HttpError as error:
            raise Exception(f"Error syncing {pdf_file}: {error}") from error
