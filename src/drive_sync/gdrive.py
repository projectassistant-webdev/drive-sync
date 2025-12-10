"""
Google Drive Tool - Enhanced file and image upload operations.

Provides:
- Image upload from bytes
- Public URL generation
- Folder creation
"""

import logging
from typing import Dict, Any, Optional
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaInMemoryUpload
from google.oauth2 import service_account


logger = logging.getLogger(__name__)


SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/drive.file'
]


class GoogleDriveError(Exception):
    """Base exception for Google Drive operations"""
    pass


class GoogleDriveService:
    """
    Google Drive service wrapper for file operations.
    """

    def __init__(self, credentials_path: str):
        """
        Initialize Google Drive service.

        Args:
            credentials_path: Path to service account credentials JSON
        """
        self.credentials_path = credentials_path
        self.service = None
        self._authenticate()

    def _authenticate(self):
        """Authenticate with Google Drive API"""
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
            logger.error(f"Authentication failed: {str(e)}")
            raise GoogleDriveError(f"Authentication failed: {str(e)}")

    def upload_image_bytes(
        self,
        image_bytes: bytes,
        filename: str,
        folder_id: str,
        mime_type: str = 'image/png',
        shared_drive_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Upload image from bytes to Google Drive.

        Args:
            image_bytes: Image data as bytes
            filename: Name for the file in Drive
            folder_id: Folder ID to upload to
            mime_type: MIME type of the image (default: image/png)
            shared_drive_id: Shared Drive ID if applicable

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
            raise GoogleDriveError(f"Failed to upload image: {error}")

    def create_folder(
        self,
        name: str,
        parent_id: str,
        shared_drive_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a folder in Google Drive.

        Args:
            name: Folder name
            parent_id: Parent folder ID
            shared_drive_id: Shared Drive ID if applicable

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
            raise GoogleDriveError(f"Failed to create folder: {error}")

    def get_public_url(
        self,
        file_id: str,
        shared_drive_id: Optional[str] = None
    ) -> str:
        """
        Get direct public URL for an image (for embedding).

        Args:
            file_id: File ID
            shared_drive_id: Shared Drive ID if applicable

        Returns:
            str: Public URL for direct embedding
        """
        # Google Drive direct download URL format
        return f"https://drive.google.com/uc?export=view&id={file_id}"

    def set_public_permissions(
        self,
        file_id: str,
        shared_drive_id: Optional[str] = None
    ) -> None:
        """
        Make file publicly readable.

        Args:
            file_id: File ID
            shared_drive_id: Shared Drive ID if applicable

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
            raise GoogleDriveError(f"Failed to set permissions: {error}")

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
            raise GoogleDriveError(f"Failed to add service account permission: {error}")
