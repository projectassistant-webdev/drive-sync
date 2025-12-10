"""
Google Drive authentication module
"""

import os
from pathlib import Path
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


SCOPES = ['https://www.googleapis.com/auth/drive.file']


class GoogleAuthenticator:
    """Handle Google Drive authentication"""

    def __init__(self, credentials_file='credentials.json'):
        """
        Initialize authenticator

        Args:
            credentials_file: Path to service account JSON file
        """
        self.credentials_file = Path(credentials_file)
        self._service = None

    def authenticate(self):
        """
        Authenticate with Google Drive API

        Returns:
            Google Drive service object

        Raises:
            FileNotFoundError: If credentials file doesn't exist
            ValueError: If credentials are invalid
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
                scopes=SCOPES
            )
            self._service = build('drive', 'v3', credentials=creds)
            return self._service

        except Exception as e:
            raise ValueError(f"Invalid credentials file: {e}")

    @property
    def service(self):
        """Get or create Google Drive service"""
        if self._service is None:
            self._service = self.authenticate()
        return self._service

    def test_connection(self):
        """
        Test Google Drive API connection

        Returns:
            bool: True if connection successful

        Raises:
            HttpError: If connection fails
        """
        try:
            # Try to list files (limit 1) to test connection
            self.service.files().list(pageSize=1).execute()
            return True
        except HttpError as error:
            raise HttpError(f"Connection test failed: {error}")
