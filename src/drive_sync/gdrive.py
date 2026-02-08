"""
Google Drive Tool - Enhanced file and image upload operations.

Provides:
- Image upload from bytes
- Public URL generation
- Folder creation
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaInMemoryUpload

logger = logging.getLogger(__name__)


SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/drive.file'
]


class GoogleDriveError(Exception):
    """Base exception for Google Drive operations"""
    pass


class GoogleDriveService:
    """Google Drive service wrapper for file operations.

    Supports two initialization modes:
    - **New (preferred):** Pass a ``GoogleAuthenticator`` instance to share
      credentials with other services.
    - **Legacy:** Pass a credentials file path (string). The service will
      authenticate independently for backward compatibility.
    """

    def __init__(self, credentials_path_or_auth: Any = None, *, credentials_path: str | None = None) -> None:
        """Initialize Google Drive service.

        Args:
            credentials_path_or_auth: Either a ``GoogleAuthenticator`` instance
                (new style) or a credentials file path string (legacy style).
            credentials_path: Explicit credentials file path (legacy keyword arg).
                Used only if ``credentials_path_or_auth`` is not provided.
        """
        from .auth import GoogleAuthenticator

        if isinstance(credentials_path_or_auth, GoogleAuthenticator):
            # New style: share credentials from authenticator
            self._auth = credentials_path_or_auth
            self.credentials_path = str(self._auth.credentials_file)
            self.service = self._auth.drive_service
            logger.info("GoogleDriveService initialized with shared authenticator")
        else:
            # Legacy style: authenticate independently with file path
            path = credentials_path_or_auth or credentials_path
            if path is None:
                raise GoogleDriveError("credentials_path is required")
            self.credentials_path = path
            self._auth = None
            self.service = None
            self._authenticate()

    def _authenticate(self) -> None:
        """Authenticate with Google Drive API (legacy path)."""
        try:
            if not Path(self.credentials_path).exists():
                raise GoogleDriveError(
                    f"Credentials not found: {self.credentials_path}"
                )

            credentials = service_account.Credentials.from_service_account_file(
                self.credentials_path,
                scopes=SCOPES
            )

            self.service = build('drive', 'v3', credentials=credentials)
            logger.info("Authenticated with Google Drive API")

        except Exception as e:
            logger.error(f"Authentication failed: {e!s}")
            raise GoogleDriveError(f"Authentication failed: {e!s}") from e

    def upload_image_bytes(
        self,
        image_bytes: bytes,
        filename: str,
        folder_id: str,
        mime_type: str = 'image/png',
    ) -> dict[str, Any]:
        """
        Upload image from bytes to Google Drive.

        Args:
            image_bytes: Image data as bytes
            filename: Name for the file in Drive
            folder_id: Folder ID to upload to
            mime_type: MIME type of the image (default: image/png)

        Returns:
            Dict: File metadata with id, name, and webViewLink

        Raises:
            GoogleDriveError: If upload fails
        """
        try:
            file_metadata = {
                'name': filename,
                'parents': [folder_id]
            }

            media = MediaInMemoryUpload(
                image_bytes,
                mimetype=mime_type,
                resumable=True
            )

            # Build request parameters
            create_params = {
                'body': file_metadata,
                'media_body': media,
                'fields': 'id, name, webViewLink, webContentLink',
                'supportsAllDrives': True  # Always support Shared Drives
            }

            file = self.service.files().create(**create_params).execute()

            logger.info(
                f"Uploaded image: {file['name']} "
                f"({len(image_bytes)} bytes, ID: {file['id']})"
            )

            return {
                'id': file['id'],
                'name': file['name'],
                'webViewLink': file.get('webViewLink'),
                'webContentLink': file.get('webContentLink')
            }

        except HttpError as error:
            logger.error(f"Failed to upload image: {error}")
            raise GoogleDriveError(f"Failed to upload image: {error}") from error

    def create_folder(
        self,
        name: str,
        parent_id: str,
    ) -> dict[str, Any]:
        """
        Create a folder in Google Drive.

        Args:
            name: Folder name
            parent_id: Parent folder ID

        Returns:
            Dict: Folder metadata with id and name

        Raises:
            GoogleDriveError: If creation fails
        """
        try:
            file_metadata = {
                'name': name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [parent_id]
            }

            create_params = {
                'body': file_metadata,
                'fields': 'id, name',
                'supportsAllDrives': True  # Always support Shared Drives
            }

            folder = self.service.files().create(**create_params).execute()

            logger.info(f"Created folder: {folder['name']} (ID: {folder['id']})")

            return {
                'id': folder['id'],
                'name': folder['name']
            }

        except HttpError as error:
            logger.error(f"Failed to create folder: {error}")
            raise GoogleDriveError(f"Failed to create folder: {error}") from error

    def get_public_url(
        self,
        file_id: str,
    ) -> str:
        """
        Get direct public URL for an image (for embedding).

        Args:
            file_id: File ID

        Returns:
            str: Public URL for direct embedding
        """
        # Google Drive direct download URL format
        return f"https://drive.google.com/uc?export=view&id={file_id}"

    def set_public_permissions(
        self,
        file_id: str,
    ) -> None:
        """
        Make file publicly readable.

        Args:
            file_id: File ID

        Raises:
            GoogleDriveError: If permission setting fails
        """
        try:
            permission = {
                'type': 'anyone',
                'role': 'reader'
            }

            create_params = {
                'fileId': file_id,
                'body': permission,
                'sendNotificationEmail': False,
                'supportsAllDrives': True  # Always support Shared Drives
            }

            self.service.permissions().create(**create_params).execute()

            logger.info(f"Set public permissions on {file_id}")

        except HttpError as error:
            logger.error(f"Failed to set permissions: {error}")
            raise GoogleDriveError(f"Failed to set permissions: {error}") from error

    def list_files(self, folder_id: str) -> list[dict[str, str]]:
        """List all non-folder files in a Google Drive folder.

        Queries the Drive API with pagination support and filters out
        folders, returning only regular files.

        Args:
            folder_id: Google Drive folder ID to list.

        Returns:
            List of dicts with 'id' and 'name' keys for each file.

        Raises:
            GoogleDriveError: If the API call fails.
        """
        try:
            all_files: list[dict[str, str]] = []
            page_token: str | None = None

            while True:
                params: dict = {
                    'q': (
                        f"'{folder_id}' in parents and trashed=false"
                        " and mimeType != 'application/vnd.google-apps.folder'"
                    ),
                    'spaces': 'drive',
                    'fields': 'nextPageToken, files(id, name, mimeType)',
                    'supportsAllDrives': True,
                    'includeItemsFromAllDrives': True,
                }
                if page_token:
                    params['pageToken'] = page_token

                response = self.service.files().list(**params).execute()

                files = response.get('files', [])
                for f in files:
                    all_files.append({'id': f['id'], 'name': f['name']})

                page_token = response.get('nextPageToken')
                if not page_token:
                    break

            logger.info(f"Listed {len(all_files)} files in folder {folder_id}")
            return all_files

        except HttpError as error:
            logger.error(f"Failed to list files in folder {folder_id}: {error}")
            raise GoogleDriveError(f"Failed to list files in folder {folder_id}: {error}") from error

    def add_service_account_reader(
        self,
        file_id: str
    ) -> None:
        """
        Add service account as reader (for Shared Drive files).

        Args:
            file_id: File ID

        Raises:
            GoogleDriveError: If permission setting fails
        """
        try:
            # Get service account email from credentials
            credentials = service_account.Credentials.from_service_account_file(
                self.credentials_path,
                scopes=SCOPES
            )
            service_account_email = credentials.service_account_email

            permission = {
                'type': 'user',
                'role': 'reader',
                'emailAddress': service_account_email
            }

            create_params = {
                'fileId': file_id,
                'body': permission,
                'sendNotificationEmail': False,
                'supportsAllDrives': True
            }

            self.service.permissions().create(**create_params).execute()

            logger.info(f"Added service account reader permission on {file_id}")

        except HttpError as error:
            logger.error(f"Failed to add service account permission: {error}")
            raise GoogleDriveError(f"Failed to add service account permission: {error}") from error
