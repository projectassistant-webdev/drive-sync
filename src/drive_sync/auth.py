"""
Google API authentication module.

Provides a single authentication point for all Google API services
(Drive v3, Docs v1) with lazy initialization. Credentials are created
once and shared across all service clients.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

# Combined scopes for all Google API services used by drive-sync
ALL_SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/documents',
]

# Legacy scope kept for backward compatibility
SCOPES = ['https://www.googleapis.com/auth/drive.file']


class GoogleAuthenticator:
    """Handle Google API authentication with lazy service initialization.

    Creates credentials once and provides lazy-initialized properties
    for each API service (Drive v3, Docs v1). This avoids authenticating
    three times at startup when only some services may be needed.

    Args:
        credentials_file: Path to service account JSON file.
        scopes: OAuth scopes to request. Defaults to ALL_SCOPES.
    """

    def __init__(self, credentials_file: str | Path = 'credentials.json', scopes: list[str] | None = None) -> None:
        """Initialize authenticator.

        Args:
            credentials_file: Path to service account JSON file.
            scopes: OAuth scopes to request. Defaults to ALL_SCOPES
                which covers Drive, Drive.file, and Documents APIs.
        """
        self.credentials_file = Path(credentials_file)
        self.scopes = scopes or ALL_SCOPES
        self._credentials: Any = None
        self._drive_service: Any = None
        self._docs_service: Any = None
        # Legacy attribute for backward compatibility
        self._service: Any = None

    @property
    def credentials(self) -> Any:
        """Get or create Google API credentials (lazy).

        Returns:
            google.oauth2.service_account.Credentials: Authenticated credentials.

        Raises:
            FileNotFoundError: If credentials file doesn't exist.
            ValueError: If credentials are invalid.
        """
        if self._credentials is None:
            self._credentials = self._create_credentials()
        return self._credentials

    @property
    def drive_service(self) -> Any:
        """Get or create Google Drive API v3 service (lazy).

        Returns:
            googleapiclient.discovery.Resource: Drive API service.
        """
        if self._drive_service is None:
            self._drive_service = build('drive', 'v3', credentials=self.credentials)
            logger.info("Initialized Google Drive API v3 service")
        return self._drive_service

    @property
    def docs_service(self) -> Any:
        """Get or create Google Docs API v1 service (lazy).

        Returns:
            googleapiclient.discovery.Resource: Docs API service.
        """
        if self._docs_service is None:
            self._docs_service = build('docs', 'v1', credentials=self.credentials)
            logger.info("Initialized Google Docs API v1 service")
        return self._docs_service

    def _create_credentials(self) -> Any:
        """Create Google API credentials from service account file.

        Returns:
            google.oauth2.service_account.Credentials: Authenticated credentials.

        Raises:
            FileNotFoundError: If credentials file doesn't exist.
            ValueError: If credentials are invalid.
        """
        if not self.credentials_file.exists():
            raise FileNotFoundError(
                f"Credentials file not found: {self.credentials_file}\n\n"
                "Setup instructions:\n"
                "1. Go to https://console.cloud.google.com\n"
                "2. Create a project and enable Google Drive API\n"
                "3. Create a service account\n"
                "4. Download JSON key as 'credentials.json'\n"
                "5. Place it in tools/drive-sync/\n"
                "6. Share Google Drive folder with service account email\n\n"
                "See: tools/drive-sync/README.md for detailed setup"
            )

        try:
            creds = service_account.Credentials.from_service_account_file(
                str(self.credentials_file),
                scopes=self.scopes
            )
            logger.info("Created Google API credentials")
            return creds
        except Exception as e:
            raise ValueError(f"Invalid credentials file: {e}") from e

    def authenticate(self) -> Any:
        """Authenticate and return a Google Drive v3 service.

        This is a backward-compatible method. New code should use
        the ``drive_service`` property instead.

        Returns:
            googleapiclient.discovery.Resource: Drive API v3 service.

        Raises:
            FileNotFoundError: If credentials file doesn't exist.
            ValueError: If credentials are invalid.
        """
        self._service = self.drive_service
        return self._service

    @property
    def service(self) -> Any:
        """Get or create Google Drive service (backward compatibility).

        Returns:
            googleapiclient.discovery.Resource: Drive API v3 service.
        """
        if self._service is None:
            self._service = self.drive_service
        return self._service

    def test_connection(self) -> bool:
        """Test Google Drive API connection.

        Returns:
            True if connection successful.

        Raises:
            HttpError: If connection fails.
        """
        try:
            # Try to list files (limit 1) to test connection
            self.drive_service.files().list(pageSize=1).execute()
            return True
        except HttpError as error:
            raise HttpError(f"Connection test failed: {error}") from error
