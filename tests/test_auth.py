"""
Tests for Google API authentication module.

Tests GoogleAuthenticator initialization, lazy credential loading,
service creation, and error handling for missing credentials.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.drive_sync.auth import ALL_SCOPES, GoogleAuthenticator


class TestGoogleAuthenticatorInit:
    """Test GoogleAuthenticator initialization."""

    def test_default_credentials_file(self):
        """Test default credentials file path."""
        auth = GoogleAuthenticator()
        assert auth.credentials_file == Path("credentials.json")

    def test_custom_credentials_file(self):
        """Test custom credentials file path."""
        auth = GoogleAuthenticator(credentials_file="/tmp/my_creds.json")
        assert auth.credentials_file == Path("/tmp/my_creds.json")

    def test_default_scopes(self):
        """Test that default scopes include all required APIs."""
        auth = GoogleAuthenticator()
        assert auth.scopes == ALL_SCOPES
        assert "https://www.googleapis.com/auth/drive" in auth.scopes
        assert "https://www.googleapis.com/auth/documents" in auth.scopes

    def test_custom_scopes(self):
        """Test that custom scopes override defaults."""
        custom = ["https://www.googleapis.com/auth/drive.readonly"]
        auth = GoogleAuthenticator(scopes=custom)
        assert auth.scopes == custom

    def test_lazy_init_credentials_none(self):
        """Test that credentials are not created during init."""
        auth = GoogleAuthenticator()
        assert auth._credentials is None
        assert auth._drive_service is None
        assert auth._docs_service is None


class TestCredentialCreation:
    """Test credential creation from service account file."""

    @patch("src.drive_sync.auth.service_account.Credentials.from_service_account_file")
    def test_credentials_created_on_access(self, mock_from_file, tmp_path):
        """Test that accessing credentials property triggers creation."""
        creds_file = tmp_path / "credentials.json"
        creds_file.write_text('{"type": "service_account"}')

        mock_creds = MagicMock()
        mock_from_file.return_value = mock_creds

        auth = GoogleAuthenticator(credentials_file=str(creds_file))
        result = auth.credentials

        assert result == mock_creds
        mock_from_file.assert_called_once_with(
            str(creds_file),
            scopes=ALL_SCOPES,
        )

    @patch("src.drive_sync.auth.service_account.Credentials.from_service_account_file")
    def test_credentials_cached_after_first_access(self, mock_from_file, tmp_path):
        """Test that credentials are only created once (cached)."""
        creds_file = tmp_path / "credentials.json"
        creds_file.write_text('{"type": "service_account"}')
        mock_from_file.return_value = MagicMock()

        auth = GoogleAuthenticator(credentials_file=str(creds_file))
        _ = auth.credentials
        _ = auth.credentials  # Second access

        # Should only create credentials once
        mock_from_file.assert_called_once()

    def test_missing_credentials_raises_file_not_found(self):
        """Test that missing credentials file raises FileNotFoundError."""
        auth = GoogleAuthenticator(credentials_file="/nonexistent/path.json")
        with pytest.raises(FileNotFoundError, match="Credentials file not found"):
            _ = auth.credentials

    @patch("src.drive_sync.auth.service_account.Credentials.from_service_account_file")
    def test_invalid_credentials_raises_value_error(self, mock_from_file, tmp_path):
        """Test that invalid credentials file raises ValueError."""
        creds_file = tmp_path / "credentials.json"
        creds_file.write_text("not valid json")
        mock_from_file.side_effect = Exception("Invalid file")

        auth = GoogleAuthenticator(credentials_file=str(creds_file))
        with pytest.raises(ValueError, match="Invalid credentials file"):
            _ = auth.credentials


class TestServiceProperties:
    """Test lazy-initialized service properties."""

    @patch("src.drive_sync.auth.build")
    @patch("src.drive_sync.auth.service_account.Credentials.from_service_account_file")
    def test_drive_service_lazy_init(self, mock_from_file, mock_build, tmp_path):
        """Test that drive_service is lazily initialized."""
        creds_file = tmp_path / "credentials.json"
        creds_file.write_text('{}')
        mock_creds = MagicMock()
        mock_from_file.return_value = mock_creds
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        auth = GoogleAuthenticator(credentials_file=str(creds_file))
        result = auth.drive_service

        assert result == mock_service
        mock_build.assert_called_once_with("drive", "v3", credentials=mock_creds)

    @patch("src.drive_sync.auth.build")
    @patch("src.drive_sync.auth.service_account.Credentials.from_service_account_file")
    def test_docs_service_lazy_init(self, mock_from_file, mock_build, tmp_path):
        """Test that docs_service is lazily initialized."""
        creds_file = tmp_path / "credentials.json"
        creds_file.write_text('{}')
        mock_creds = MagicMock()
        mock_from_file.return_value = mock_creds
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        auth = GoogleAuthenticator(credentials_file=str(creds_file))
        result = auth.docs_service

        assert result == mock_service
        mock_build.assert_called_once_with("docs", "v1", credentials=mock_creds)

    @patch("src.drive_sync.auth.build")
    @patch("src.drive_sync.auth.service_account.Credentials.from_service_account_file")
    def test_service_cached_after_first_access(self, mock_from_file, mock_build, tmp_path):
        """Test that services are only built once."""
        creds_file = tmp_path / "credentials.json"
        creds_file.write_text('{}')
        mock_from_file.return_value = MagicMock()
        mock_build.return_value = MagicMock()

        auth = GoogleAuthenticator(credentials_file=str(creds_file))
        _ = auth.drive_service
        _ = auth.drive_service

        # build() should be called only once for drive
        assert mock_build.call_count == 1


class TestBackwardCompatibility:
    """Test backward-compatible authenticate() method and service property."""

    @patch("src.drive_sync.auth.build")
    @patch("src.drive_sync.auth.service_account.Credentials.from_service_account_file")
    def test_authenticate_returns_drive_service(self, mock_from_file, mock_build, tmp_path):
        """Test that authenticate() returns Drive service for backward compat."""
        creds_file = tmp_path / "credentials.json"
        creds_file.write_text('{}')
        mock_from_file.return_value = MagicMock()
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        auth = GoogleAuthenticator(credentials_file=str(creds_file))
        result = auth.authenticate()

        assert result == mock_service

    @patch("src.drive_sync.auth.build")
    @patch("src.drive_sync.auth.service_account.Credentials.from_service_account_file")
    def test_service_property_backward_compat(self, mock_from_file, mock_build, tmp_path):
        """Test that service property returns Drive service."""
        creds_file = tmp_path / "credentials.json"
        creds_file.write_text('{}')
        mock_from_file.return_value = MagicMock()
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        auth = GoogleAuthenticator(credentials_file=str(creds_file))
        result = auth.service

        assert result == mock_service


class TestConnectionTest:
    """Test the test_connection method."""

    @patch("src.drive_sync.auth.build")
    @patch("src.drive_sync.auth.service_account.Credentials.from_service_account_file")
    def test_successful_connection(self, mock_from_file, mock_build, tmp_path):
        """Test successful connection test."""
        creds_file = tmp_path / "credentials.json"
        creds_file.write_text('{}')
        mock_from_file.return_value = MagicMock()

        mock_service = MagicMock()
        mock_service.files().list().execute.return_value = {"files": []}
        mock_build.return_value = mock_service

        auth = GoogleAuthenticator(credentials_file=str(creds_file))
        result = auth.test_connection()

        assert result is True
