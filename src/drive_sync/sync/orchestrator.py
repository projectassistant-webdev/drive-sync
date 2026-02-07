"""
Core sync orchestration for Google Drive with Mermaid diagram and image support.

Contains the main ``GoogleDriveSync`` class that coordinates file syncing,
inheriting content processing from ``ProcessorMixin`` and upload logic
from ``UploaderMixin``.

Enhanced workflow:
1. Extract Mermaid diagrams from markdown
2. Extract local image references from markdown
3. Upload markdown to Google Docs (with [DIAGRAM:name] and [IMAGE:name] markers)
4. Render Mermaid diagrams as PNG images via mermaid.ink API
5. Upload local images to Google Drive
6. Embed images at marker positions in Google Docs
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

from googleapiclient.errors import HttpError

from ..auth import GoogleAuthenticator
from ..cache import SyncCache
from ..converter import CSVConverter, FileTypeDetector, MarkdownConverter, PDFConverter
from ..gdocs import GoogleDocsService
from ..gdrive import GoogleDriveService
from .processors import ProcessorMixin
from .uploaders import UploaderMixin

logger = logging.getLogger(__name__)

# Named constants for default configuration values
DEFAULT_RATE_LIMIT_DELAY = 0.5
DEFAULT_BATCH_SIZE = 10


class GoogleDriveSync(ProcessorMixin, UploaderMixin):
    """Main sync class for uploading files to Google Drive with Mermaid support.

    Coordinates file detection, upload, and content embedding across
    Google Drive and Google Docs APIs. Uses a single ``GoogleAuthenticator``
    instance for all API interactions.
    """

    def __init__(
        self,
        credentials_file: str | Path = 'credentials.json',
        folder_id: str | None = None,
        use_cache: bool = True,
        rate_limit_delay: float = DEFAULT_RATE_LIMIT_DELAY,
        batch_size: int = DEFAULT_BATCH_SIZE,
        enable_mermaid: bool = True
    ) -> None:
        """Initialize Google Drive sync with Mermaid support.

        Args:
            credentials_file: Path to service account JSON.
            folder_id: Optional Google Drive folder ID to sync to.
            use_cache: Whether to use caching system (default: True).
            rate_limit_delay: Delay in seconds between API calls (default: 0.5).
            batch_size: Number of files to sync before saving cache (default: 10).
            enable_mermaid: Whether to process Mermaid diagrams (default: True).
        """
        # Single authenticator for all services (REQ-3.2)
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

        # Initialize enhanced services using shared authenticator (REQ-3.2)
        self.gdocs_service = None
        self.gdrive_service = None
        if enable_mermaid:
            self.gdocs_service = GoogleDocsService(self.auth)
            self.gdrive_service = GoogleDriveService(self.auth)

        if self.use_cache:
            self.cache.load()

        logger.info(
            f"Initialized GoogleDriveSync "
            f"(mermaid={'enabled' if enable_mermaid else 'disabled'})"
        )

    def _rate_limit(self) -> None:
        """Apply rate limiting between API calls."""
        if self.rate_limit_delay > 0:
            elapsed = time.time() - self.last_api_call
            if elapsed < self.rate_limit_delay:
                time.sleep(self.rate_limit_delay - elapsed)
        self.last_api_call = time.time()
        self.api_call_count += 1

    def _execute_with_retry(self, request: Any, max_retries: int = 5) -> Any:
        """Execute Google Drive API request with exponential backoff retry logic.

        Args:
            request: Google API request object.
            max_retries: Maximum number of retry attempts.

        Returns:
            API response.

        Raises:
            HttpError: If all retries are exhausted.
            Exception: If unexpected error occurs.
        """
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

    def get_or_create_folder(self, name: str, parent_id: str | None = None) -> str:
        """Get existing folder or create if it doesn't exist.

        Args:
            name: Folder name.
            parent_id: Parent folder ID (defaults to self.folder_id or 'root').

        Returns:
            Google Drive folder ID.
        """
        parent_id = parent_id or self.folder_id or 'root'

        try:
            # Search for existing folder
            query = (
                f"name='{name}' and mimeType='application/vnd.google-apps.folder' "
                f"and '{parent_id}' in parents and trashed=false"
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

            if files:
                logger.info(f"Found existing folder: {name}")
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
            logger.info(f"Created folder: {name}")
            return folder['id']

        except HttpError as error:
            raise Exception(f"Error with folder '{name}': {error}") from error

    def sync_file(self, file_path: Path, folder_id: str | None = None) -> str | None:
        """Auto-detect file type and sync to Google Drive.

        Args:
            file_path: Path to the file to sync.
            folder_id: Target Google Drive folder ID.

        Returns:
            Google Drive file ID, or None if file type not supported.
        """
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
            logger.warning(f"Skipped: {file_path} - {e}")
            return None

    def sync_directory(self, directory: Path, recursive: bool = True, exclude: list[str] | None = None) -> dict[str, str]:
        """Sync entire directory to Google Drive with Mermaid support.

        Args:
            directory: Path to directory to sync.
            recursive: Whether to recurse into subdirectories.
            exclude: List of glob patterns to exclude.

        Returns:
            Dict mapping file paths to their Google Drive IDs.
        """
        directory = Path(directory)
        exclude = exclude or []
        synced_files = {}

        # Create folder structure
        logger.info("Creating folder structure...")
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
            logger.info(f"Skipping {ignored_count} ignored file(s) (.gitkeep, media files, etc.)")

        total_files = len(files)
        logger.info(f"\nFound {total_files} files to process\n")

        # Sync each file with progress tracking
        for idx, file_path in enumerate(files, 1):
            parent_dir = str(file_path.parent)
            target_folder = folders.get(parent_dir, self.folder_id or 'root')

            try:
                logger.info(f"[{idx}/{total_files}] Processing file")
                file_id = self.sync_file(file_path, target_folder)
                if file_id:
                    synced_files[str(file_path)] = file_id

                # Batch save cache
                if self.use_cache and idx % self.batch_size == 0:
                    self.cache.save()
                    logger.info(f"Progress saved ({idx}/{total_files} files)")

            except Exception as e:
                logger.error(f"Error syncing {file_path}: {e}")

        # Final cache save
        if self.use_cache:
            self.cache.save()
            logger.info(f"\nFinal sync cache saved ({len(synced_files)}/{total_files} successful)")

        # Summary
        logger.info("\nSync Statistics:")
        logger.info(f"   Total files: {total_files}")
        logger.info(f"   Successfully synced: {len(synced_files)}")
        logger.info(f"   Errors: {total_files - len(synced_files)}")
        logger.info(f"   API calls made: {self.api_call_count}")

        return synced_files

    def create_folder_structure(self, base_path: Path, parent_id: str | None = None) -> dict[str, str]:
        """Create folder structure matching local directory.

        For paths like 'projects/student_einstein/scope', creates:
        - student_einstein/ (project folder)
        - student_einstein/scope/ (scope subfolder)

        This preserves the project name in the Drive hierarchy.

        Args:
            base_path: Local directory path.
            parent_id: Parent folder ID in Google Drive.

        Returns:
            Dict mapping local directory paths to Google Drive folder IDs.
        """
        folders = {}
        parent_id = parent_id or self.folder_id or 'root'

        # Check if this is a nested project path (e.g., projects/client/scope)
        # If so, we want to create the parent folder (client) first
        path_parts = base_path.parts

        # Look for common patterns: projects/client_name/scope or projects/client_name/context
        if len(path_parts) >= 3 and path_parts[-3] == 'projects':
            # Create project folder first (e.g., "student_einstein")
            project_name = path_parts[-2]  # The client/project name
            project_folder_id = self.get_or_create_folder(project_name, parent_id)

            # Then create the subfolder (e.g., "scope")
            subfolder_name = path_parts[-1]
            main_folder_id = self.get_or_create_folder(subfolder_name, project_folder_id)
            folders[str(base_path)] = main_folder_id
        else:
            # Standard behavior for non-nested paths
            main_folder_name = base_path.name
            main_folder_id = self.get_or_create_folder(main_folder_name, parent_id)
            folders[str(base_path)] = main_folder_id

        for subdir in base_path.rglob('*'):
            if subdir.is_dir():
                parent_path = subdir.parent

                parent_folder_id = folders.get(str(parent_path), main_folder_id)

                folder_id = self.get_or_create_folder(subdir.name, parent_folder_id)
                folders[str(subdir)] = folder_id

        return folders

    def finalize(self) -> None:
        """Save cache before shutdown."""
        if self.use_cache and self.cache:
            self.cache.save()
