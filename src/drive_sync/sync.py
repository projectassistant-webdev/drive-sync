"""
Core synchronization logic for Docs-to-Drive with Mermaid diagram and image support.

Enhanced workflow:
1. Extract Mermaid diagrams from markdown
2. Extract local image references from markdown
3. Upload markdown to Google Docs (with [DIAGRAM:name] and [IMAGE:name] markers)
4. Render Mermaid diagrams as PNG images via mermaid.ink API
5. Upload local images to Google Drive
6. Embed images at marker positions in Google Docs
"""

import os
import time
import logging
from pathlib import Path
from typing import Optional, List, Dict
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

from .auth import GoogleAuthenticator
from .converter import FileTypeDetector, MarkdownConverter, CSVConverter, PDFConverter
from .cache import SyncCache
from .mermaid_api import render_mermaid_diagram, get_mermaid_url, MermaidAPIError, MermaidCLIError
from .gdocs import GoogleDocsService
from .gdrive import GoogleDriveService

logger = logging.getLogger(__name__)


class GoogleDriveSync:
    """Main sync class for uploading files to Google Drive with Mermaid support"""

    def __init__(
        self,
        credentials_file='credentials.json',
        folder_id: Optional[str] = None,
        use_cache: bool = True,
        rate_limit_delay: float = 0.5,
        batch_size: int = 10,
        enable_mermaid: bool = True
    ):
        """
        Initialize Google Drive sync with Mermaid support.

        Args:
            credentials_file: Path to service account JSON
            folder_id: Optional Google Drive folder ID to sync to
            use_cache: Whether to use caching system (default: True)
            rate_limit_delay: Delay in seconds between API calls (default: 0.5)
            batch_size: Number of files to sync before saving cache (default: 10)
            enable_mermaid: Whether to process Mermaid diagrams (default: True)
        """
        self.auth = GoogleAuthenticator(credentials_file)
        self.service = self.auth.authenticate()
        self.folder_id = folder_id or os.getenv('GOOGLE_DRIVE_FOLDER_ID')
        self.use_cache = use_cache
        # Pass folder_id to cache for project-specific cache files
        self.cache = SyncCache(folder_id=self.folder_id) if use_cache else None
        self.rate_limit_delay = rate_limit_delay
        self.batch_size = batch_size
        self.api_call_count = 0
        self.last_api_call = 0
        self.enable_mermaid = enable_mermaid

        # Initialize enhanced services for Mermaid support
        self.gdocs_service = None
        self.gdrive_service = None
        if enable_mermaid:
            self.gdocs_service = GoogleDocsService(credentials_file)
            self.gdrive_service = GoogleDriveService(credentials_file)

        if self.use_cache:
            self.cache.load()

        logger.info(
            f"Initialized GoogleDriveSync "
            f"(mermaid={'enabled' if enable_mermaid else 'disabled'})"
        )

    def _rate_limit(self):
        """Apply rate limiting between API calls"""
        if self.rate_limit_delay > 0:
            elapsed = time.time() - self.last_api_call
            if elapsed < self.rate_limit_delay:
                time.sleep(self.rate_limit_delay - elapsed)
        self.last_api_call = time.time()
        self.api_call_count += 1

    def _execute_with_retry(self, request, max_retries: int = 5):
        """Execute Google Drive API request with exponential backoff retry logic"""
        for attempt in range(max_retries):
            try:
                self._rate_limit()
                return request.execute()
            except HttpError as error:
                if error.resp.status == 429:  # Rate limit
                    wait_time = (2 ** attempt) + (time.time() % 1)
                    logger.warning(f"Rate limit hit, waiting {wait_time:.1f}s (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                    if attempt == max_retries - 1:
                        raise
                elif error.resp.status >= 500:  # Server error
                    wait_time = (2 ** attempt)
                    logger.warning(f"Server error, retrying in {wait_time:.1f}s (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                    if attempt == max_retries - 1:
                        raise
                else:
                    raise
        raise Exception("Unexpected error in retry logic")

    def get_or_create_folder(self, name: str, parent_id: Optional[str] = None) -> str:
        """Get existing folder or create if it doesn't exist"""
        parent_id = parent_id or self.folder_id or 'root'

        try:
            # Search for existing folder
            query = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and '{parent_id}' in parents and trashed=false"
            request = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name)',
                supportsAllDrives=True,
                includeItemsFromAllDrives=True
            )
            results = self._execute_with_retry(request)
            files = results.get('files', [])

            if files:
                logger.info(f"📁 Found existing folder: {name}")
                return files[0]['id']

            # Create new folder
            folder_metadata = {
                'name': name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            if parent_id:
                folder_metadata['parents'] = [parent_id]

            request = self.service.files().create(
                body=folder_metadata,
                fields='id',
                supportsAllDrives=True
            )
            folder = self._execute_with_retry(request)
            logger.info(f"📁 Created folder: {name}")
            return folder['id']

        except HttpError as error:
            raise Exception(f"Error with folder '{name}': {error}")

    def markdown_to_doc_with_diagrams(
        self,
        md_file: Path,
        folder_id: Optional[str] = None,
        custom_name: Optional[str] = None,
        enable_images: bool = True
    ) -> str:
        """
        Convert markdown file to Google Docs with Mermaid diagram and image support.

        Workflow:
        1. Extract Mermaid diagrams from markdown
        2. Extract local image references from markdown
        3. Upload markdown with markers to Google Docs
        4. Render Mermaid diagrams as PNG images
        5. Upload local images to Google Drive
        6. Embed all images at marker positions

        Args:
            md_file: Path to markdown file
            folder_id: Target Google Drive folder ID
            custom_name: Optional custom name for the document
            enable_images: Whether to embed local images (default: True)

        Returns:
            Google Doc ID
        """
        md_file = Path(md_file)
        folder_id = folder_id or self.folder_id or 'root'

        # Check cache
        if self.use_cache:
            should_sync, reason = self.cache.should_sync(md_file)
            if not should_sync:
                logger.info(f"⏭️  Skipped: {md_file} ({reason})")
                return self.cache.cache[str(md_file)].get('drive_id')
            logger.info(f"📤 Syncing: {md_file} ({reason})")
        else:
            logger.info(f"📤 Syncing: {md_file}")

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

        try:
            # Check if document already exists
            query = f"name='{file_name}' and mimeType='application/vnd.google-apps.document' and '{folder_id}' in parents and trashed=false"
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
                logger.info(f"🔄 Updated: {md_file} → Google Doc")
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
                logger.info(f"✅ Created: {md_file} → Google Doc")
                doc_id = doc['id']

            # Process Mermaid diagrams if any
            if self.enable_mermaid and diagrams and self.gdocs_service and self.gdrive_service:
                logger.info(f"🎨 Processing {len(diagrams)} Mermaid diagrams...")
                self._process_mermaid_diagrams(doc_id, diagrams, folder_id)

            # Process local images if any
            if enable_images and images and self.gdocs_service and self.gdrive_service:
                logger.info(f"🖼️  Processing {len(images)} local images...")
                self._process_local_images(doc_id, images, folder_id)

            # Process anchor links if enabled
            enable_anchor_links = os.getenv('ENABLE_ANCHOR_LINKS', 'true').lower() == 'true'
            if enable_anchor_links and self.gdocs_service:
                try:
                    converted_count = self.gdocs_service.process_anchor_links(doc_id)
                    if converted_count > 0:
                        logger.info(f"🔗 Converted {converted_count} anchor links")
                except Exception as e:
                    # Don't fail entire sync if anchor conversion fails
                    logger.warning(f"⚠️  Failed to convert anchor links: {e}")

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
            raise Exception(f"Error syncing {md_file}: {error}")

    def _process_mermaid_diagrams(self, doc_id: str, diagrams: List[Dict], folder_id: str):
        """
        Process Mermaid diagrams: render and embed in document.

        Rendering strategy based on MERMAID_RENDER_MODE:
        - "local": Always render locally, upload to Drive, embed via Drive URL (most reliable)
        - "api": Use direct mermaid.ink URL when possible (original behavior, less reliable)
        - "hybrid": Try local first, fall back to API

        Args:
            doc_id: Google Doc ID
            diagrams: List of diagram dicts with 'name', 'code', 'hash'
            folder_id: Folder ID for storing diagram images
        """
        # Create subfolder for diagram images (only if needed)
        diagrams_folder_id = None
        render_mode = os.environ.get('MERMAID_RENDER_MODE', 'local').lower()

        for diagram in diagrams:
            try:
                diagram_name = diagram['name']
                diagram_code = diagram['code']

                logger.info(f"  Processing {diagram_name}...")

                # Determine if we should use local rendering (upload to Drive)
                # Local mode: ALWAYS render locally and upload to Drive (most reliable)
                # API mode: Use direct URL when under 2KB limit
                use_drive_upload = (render_mode == 'local')

                if not use_drive_upload:
                    # Check if URL would be too long for Google Docs (2KB limit)
                    mermaid_url = get_mermaid_url(
                        diagram_code,
                        format='png',
                        theme='default',
                        background_color='white'
                    )
                    if len(mermaid_url) > 2000:
                        use_drive_upload = True
                        logger.info(f"  URL too long ({len(mermaid_url)} bytes) - using Drive upload")
                    else:
                        logger.info(f"  Using direct Mermaid.ink URL ({len(mermaid_url)} bytes)")
                        image_url = mermaid_url

                if use_drive_upload:
                    # Render locally and upload to Google Drive
                    logger.info(f"  Rendering locally and uploading to Drive...")

                    # Create diagrams folder if needed
                    if not diagrams_folder_id:
                        diagrams_folder_id = self.get_or_create_folder("Diagram Images", folder_id)

                    # Render using configured backend (local CLI or API)
                    png_bytes = render_mermaid_diagram(diagram_code, format='png')

                    # Upload to Drive
                    file_metadata = self.gdrive_service.upload_image_bytes(
                        image_bytes=png_bytes,
                        filename=f"{diagram_name}.png",
                        folder_id=diagrams_folder_id,
                        mime_type='image/png'
                    )

                    # Make the file publicly readable so Google Docs can embed it
                    try:
                        self.gdrive_service.set_public_permissions(file_metadata['id'])
                        logger.info(f"  Set public read permissions")
                    except Exception as e:
                        logger.warning(f"  Could not set public permissions: {e}")

                    # Small delay to let Google Drive process the file
                    time.sleep(0.5)

                    # Use Drive view URL (works better for embedding)
                    image_url = f"https://drive.google.com/uc?export=view&id={file_metadata['id']}"
                    logger.info(f"  Uploaded to Drive ({len(png_bytes)} bytes)")

                # Step 2: Find marker in document and embed image
                markers = self.gdocs_service.find_diagram_markers(doc_id)
                matching_markers = [m for m in markers if m['name'] == diagram_name]

                if matching_markers:
                    # Use the first matching marker
                    marker = matching_markers[0]
                    self.gdocs_service.embed_diagram(
                        doc_id=doc_id,
                        diagram_name=diagram_name,
                        image_url=image_url,
                        marker_index=marker['index'],
                        marker_length=marker['length'],
                        width_pt=500,
                        height_pt=350
                    )
                    logger.info(f"  ✅ Embedded {diagram_name}")
                else:
                    logger.warning(f"  ⚠️  Marker not found for {diagram_name}")

            except (MermaidAPIError, MermaidCLIError) as e:
                logger.error(f"  ❌ Failed to render {diagram_name}: {e}")
            except Exception as e:
                logger.error(f"  ❌ Failed to process {diagram_name}: {e}")

    def _process_local_images(self, doc_id: str, images: List[Dict], folder_id: str):
        """
        Process local image files: upload to Drive and embed in document.

        Args:
            doc_id: Google Doc ID
            images: List of image dicts with 'name', 'path', 'display_name', 'alt'
            folder_id: Folder ID for storing uploaded images
        """
        # Create subfolder for images (only if needed)
        images_folder_id = None

        for image in images:
            try:
                image_name = image['name']
                image_path = Path(image['path'])
                display_name = image.get('display_name', image_name)

                logger.info(f"  Processing {display_name}...")

                if not image_path.exists():
                    logger.warning(f"  ⚠️  Image file not found: {image_path}")
                    continue

                # Read image file
                with open(image_path, 'rb') as f:
                    image_bytes = f.read()

                # Determine MIME type
                suffix = image_path.suffix.lower()
                mime_types = {
                    '.png': 'image/png',
                    '.jpg': 'image/jpeg',
                    '.jpeg': 'image/jpeg',
                    '.gif': 'image/gif',
                    '.webp': 'image/webp'
                }
                mime_type = mime_types.get(suffix, 'image/png')

                # Create images folder if needed
                if not images_folder_id:
                    images_folder_id = self.get_or_create_folder("Embedded Images", folder_id)

                # Upload to Drive
                file_metadata = self.gdrive_service.upload_image_bytes(
                    image_bytes=image_bytes,
                    filename=f"{display_name}{suffix}",
                    folder_id=images_folder_id,
                    mime_type=mime_type
                )

                # Give service account read access (works on Shared Drives)
                try:
                    self.gdrive_service.add_service_account_reader(file_metadata['id'])
                    logger.info(f"  Added service account read permission")
                except Exception as e:
                    logger.info(f"  Permission already inherited: {e}")

                # Make the file publicly readable so Google Docs can embed it
                try:
                    self.gdrive_service.set_public_permissions(file_metadata['id'])
                    logger.info(f"  Set public read permissions")
                except Exception as e:
                    logger.warning(f"  Could not set public permissions: {e}")

                # Use Google Drive direct view URL (works better for embedding)
                image_url = f"https://drive.google.com/uc?export=view&id={file_metadata['id']}"
                logger.info(f"  Uploaded to Drive ({len(image_bytes)} bytes)")

                # Find marker in document and embed image
                markers = self._find_image_markers(doc_id)
                matching_markers = [m for m in markers if m['name'] == image_name]

                if matching_markers:
                    # Use the first matching marker
                    marker = matching_markers[0]
                    # Size images at ~40% page width (Google Doc page = 612pt wide)
                    # 245pt width, maintain 16:10 aspect ratio for screenshots
                    self.gdocs_service.embed_diagram(
                        doc_id=doc_id,
                        diagram_name=image_name,
                        image_url=image_url,
                        marker_index=marker['index'],
                        marker_length=marker['length'],
                        width_pt=280,  # ~40-45% page width for reasonable sizing
                        height_pt=175  # 16:10 aspect ratio
                    )
                    logger.info(f"  ✅ Embedded {display_name}")
                else:
                    logger.warning(f"  ⚠️  Marker not found for {image_name}")

            except Exception as e:
                logger.error(f"  ❌ Failed to process {image.get('display_name', image_name)}: {e}")

    def _find_image_markers(self, doc_id: str) -> List[Dict]:
        """
        Find image markers in document ([IMAGE:name]).

        Args:
            doc_id: Document ID

        Returns:
            List[Dict]: List of marker locations with name and index
        """
        import re

        try:
            doc = self.gdocs_service.docs_service.documents().get(documentId=doc_id).execute()
            content = doc.get('body', {}).get('content', [])
            markers = []

            # Pattern for image markers
            marker_pattern = r'\[IMAGE:(\w+)\]'

            # Search through content
            for element in content:
                if 'paragraph' in element:
                    paragraph = element['paragraph']
                    for text_run in paragraph.get('elements', []):
                        if 'textRun' in text_run:
                            text_content = text_run['textRun'].get('content', '')
                            start_index = text_run.get('startIndex', 0)

                            # Find all markers in this text run
                            for match in re.finditer(marker_pattern, text_content):
                                image_name = match.group(1)
                                marker_offset = match.start()
                                marker_index = start_index + marker_offset

                                markers.append({
                                    'name': image_name,
                                    'index': marker_index,
                                    'length': len(match.group(0))
                                })

            logger.info(f"Found {len(markers)} image markers in {doc_id}")
            return markers

        except Exception as error:
            logger.error(f"Failed to find image markers: {error}")
            return []

    def csv_to_sheet(self, csv_file: Path, folder_id: Optional[str] = None, custom_name: Optional[str] = None) -> str:
        """Convert and upload CSV file to Google Sheets (existing implementation)"""
        csv_file = Path(csv_file)
        folder_id = folder_id or self.folder_id or 'root'

        converter = CSVConverter()
        file_metadata = converter.prepare_for_upload(csv_file)

        if custom_name:
            file_metadata['name'] = custom_name

        file_name = file_metadata['name']

        try:
            query = f"name='{file_name}' and mimeType='application/vnd.google-apps.spreadsheet' and '{folder_id}' in parents and trashed=false"
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
                logger.info(f"🔄 Updated: {csv_file} → Google Sheet")
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
                logger.info(f"✅ Created: {csv_file} → Google Sheet")
                logger.info(f"   View at: {sheet.get('webViewLink')}")

            return sheet['id']

        except HttpError as error:
            raise Exception(f"Error syncing {csv_file}: {error}")

    def pdf_to_drive(self, pdf_file: Path, folder_id: Optional[str] = None, custom_name: Optional[str] = None) -> str:
        """
        Upload PDF file directly to Google Drive (no conversion).

        Args:
            pdf_file: Path to PDF file
            folder_id: Target Google Drive folder ID
            custom_name: Optional custom name for the file

        Returns:
            Google Drive file ID
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
                logger.info(f"⏭️  Skipped: {pdf_file} ({reason})")
                return self.cache.cache[str(pdf_file)].get('drive_id')
            logger.info(f"📤 Syncing: {pdf_file} ({reason})")
        else:
            logger.info(f"📤 Syncing: {pdf_file}")

        try:
            # Check if PDF already exists in folder
            query = f"name='{file_name}' and mimeType='application/pdf' and '{folder_id}' in parents and trashed=false"
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
                # Update existing PDF
                request = self.service.files().update(
                    fileId=files[0]['id'],
                    media_body=media,
                    fields='id,webViewLink',
                    supportsAllDrives=True
                )
                pdf = self._execute_with_retry(request)
                logger.info(f"🔄 Updated: {pdf_file} → Google Drive PDF")
                logger.info(f"   View at: {pdf.get('webViewLink')}")
            else:
                # Create new PDF
                file_metadata['parents'] = [folder_id]

                request = self.service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id,webViewLink',
                    supportsAllDrives=True
                )
                pdf = self._execute_with_retry(request)
                logger.info(f"✅ Created: {pdf_file} → Google Drive PDF")
                logger.info(f"   View at: {pdf.get('webViewLink')}")

            # Update cache
            if self.use_cache:
                self.cache.update(pdf_file, pdf['id'])

            return pdf['id']

        except HttpError as error:
            raise Exception(f"Error syncing {pdf_file}: {error}")

    def sync_file(self, file_path: Path, folder_id: Optional[str] = None) -> str:
        """Auto-detect file type and sync to Google Drive"""
        file_path = Path(file_path)

        try:
            converter_class = FileTypeDetector.get_converter(file_path)

            if converter_class == MarkdownConverter:
                return self.markdown_to_doc_with_diagrams(file_path, folder_id)
            elif converter_class == CSVConverter:
                return self.csv_to_sheet(file_path, folder_id)
            elif converter_class == PDFConverter:
                return self.pdf_to_drive(file_path, folder_id)

        except ValueError as e:
            logger.warning(f"⚠️  Skipped: {file_path} - {e}")
            return None

    def sync_directory(self, directory: Path, recursive: bool = True, exclude: Optional[List[str]] = None) -> Dict[str, str]:
        """Sync entire directory to Google Drive with Mermaid support"""
        directory = Path(directory)
        exclude = exclude or []
        synced_files = {}

        # Create folder structure
        logger.info(f"📂 Creating folder structure...")
        folders = self.create_folder_structure(directory, self.folder_id)

        # Get files to sync
        glob_pattern = '**/*' if recursive else '*'
        files = [f for f in directory.glob(glob_pattern) if f.is_file()]

        # Filter excluded patterns
        for pattern in exclude:
            files = [f for f in files if not f.match(pattern)]

        # Filter out ignored files (like .gitkeep, .mp4, etc.)
        ignored_count = 0
        filtered_files = []
        for f in files:
            if FileTypeDetector.should_ignore(f):
                ignored_count += 1
            else:
                filtered_files.append(f)
        files = filtered_files

        if ignored_count > 0:
            logger.info(f"⏭️  Skipping {ignored_count} ignored file(s) (.gitkeep, media files, etc.)")

        total_files = len(files)
        logger.info(f"\n📊 Found {total_files} files to process\n")

        # Sync each file with progress tracking
        for idx, file_path in enumerate(files, 1):
            parent_dir = str(file_path.parent)
            target_folder = folders.get(parent_dir, self.folder_id or 'root')

            try:
                print(f"[{idx}/{total_files}] ", end="")
                file_id = self.sync_file(file_path, target_folder)
                if file_id:
                    synced_files[str(file_path)] = file_id

                # Batch save cache
                if self.use_cache and idx % self.batch_size == 0:
                    self.cache.save()
                    logger.info(f"💾 Progress saved ({idx}/{total_files} files)")

            except Exception as e:
                logger.error(f"❌ Error syncing {file_path}: {e}")

        # Final cache save
        if self.use_cache:
            self.cache.save()
            logger.info(f"\n💾 Final sync cache saved ({len(synced_files)}/{total_files} successful)")

        # Summary
        logger.info(f"\n📈 Sync Statistics:")
        logger.info(f"   Total files: {total_files}")
        logger.info(f"   Successfully synced: {len(synced_files)}")
        logger.info(f"   Errors: {total_files - len(synced_files)}")
        logger.info(f"   API calls made: {self.api_call_count}")

        return synced_files

    def create_folder_structure(self, base_path: Path, parent_id: Optional[str] = None) -> Dict[str, str]:
        """Create folder structure matching local directory"""
        folders = {}
        parent_id = parent_id or self.folder_id or 'root'

        main_folder_name = base_path.name
        main_folder_id = self.get_or_create_folder(main_folder_name, parent_id)
        folders[str(base_path)] = main_folder_id

        for subdir in base_path.rglob('*'):
            if subdir.is_dir():
                parent_path = subdir.parent

                if str(parent_path) in folders:
                    parent_folder_id = folders[str(parent_path)]
                else:
                    parent_folder_id = main_folder_id

                folder_id = self.get_or_create_folder(subdir.name, parent_folder_id)
                folders[str(subdir)] = folder_id

        return folders

    def finalize(self):
        """Save cache before shutdown"""
        if self.use_cache and self.cache:
            self.cache.save()
