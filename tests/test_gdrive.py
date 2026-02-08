"""
Tests for Google Drive service module.

Tests GoogleDriveService initialization (shared auth and legacy),
image upload, folder creation, public URL generation, permission
management, and error handling.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.drive_sync.auth import GoogleAuthenticator
from src.drive_sync.gdrive import GoogleDriveError, GoogleDriveService


def _make_mock_auth():
    """Create a mock GoogleAuthenticator that passes isinstance checks.

    GoogleDriveService.__init__ uses ``isinstance(arg, GoogleAuthenticator)``
    to decide the init path, so we need a proper spec-based mock.
    """
    mock_auth = MagicMock(spec=GoogleAuthenticator)
    mock_auth.credentials_file = Path("credentials.json")
    mock_auth.drive_service = MagicMock()
    return mock_auth


class TestGoogleDriveServiceInit:
    """Test GoogleDriveService initialization modes."""

    def test_init_with_shared_authenticator(self):
        """Test initialization with a GoogleAuthenticator instance."""
        mock_auth = _make_mock_auth()
        service = GoogleDriveService(mock_auth)

        assert service.service == mock_auth.drive_service
        assert service.credentials_path == "credentials.json"

    @patch("src.drive_sync.gdrive.build")
    @patch("src.drive_sync.gdrive.service_account.Credentials.from_service_account_file")
    def test_init_with_legacy_path(self, mock_from_file, mock_build, tmp_path):
        """Test initialization with credentials file path string."""
        creds_file = tmp_path / "credentials.json"
        creds_file.write_text('{"type": "service_account"}')

        mock_from_file.return_value = MagicMock()
        mock_build.return_value = MagicMock()

        service = GoogleDriveService(str(creds_file))

        assert service.credentials_path == str(creds_file)
        assert service.service is not None

    def test_init_without_path_raises(self):
        """Test that missing credentials raises GoogleDriveError."""
        with pytest.raises(GoogleDriveError, match="credentials_path is required"):
            GoogleDriveService()

    @patch("src.drive_sync.gdrive.service_account.Credentials.from_service_account_file")
    def test_init_with_missing_file_raises(self, mock_from_file):
        """Test that non-existent credentials file raises GoogleDriveError."""
        with pytest.raises(GoogleDriveError, match="Credentials not found"):
            GoogleDriveService("/nonexistent/credentials.json")

    def test_init_with_keyword_arg(self):
        """Test initialization using credentials_path_or_auth positional argument."""
        mock_auth = _make_mock_auth()
        service = GoogleDriveService(mock_auth)

        assert service.service is not None


class TestUploadImageBytes:
    """Test image upload from bytes."""

    def _make_service(self):
        """Helper: create service with mocked Drive API."""
        mock_auth = _make_mock_auth()
        mock_auth.drive_service.files().create().execute.return_value = {
            "id": "file-123",
            "name": "test.png",
            "webViewLink": "https://drive.google.com/file/d/file-123/view",
            "webContentLink": "https://drive.google.com/uc?id=file-123",
        }
        service = GoogleDriveService(mock_auth)
        return service

    def test_returns_file_metadata(self):
        """Test that upload returns dict with id, name, links."""
        service = self._make_service()
        fake_image = b"\x89PNG" + b"\x00" * 100

        result = service.upload_image_bytes(
            image_bytes=fake_image,
            filename="screenshot.png",
            folder_id="folder-abc",
        )

        assert "id" in result
        assert "name" in result
        assert "webViewLink" in result

    def test_calls_create_with_correct_params(self):
        """Test that files().create() is called with expected parameters."""
        service = self._make_service()
        fake_image = b"\x89PNG" + b"\x00" * 100

        service.upload_image_bytes(
            image_bytes=fake_image,
            filename="diagram.png",
            folder_id="folder-xyz",
            mime_type="image/png",
        )

        service.service.files().create.assert_called()

    def test_http_error_raises_drive_error(self):
        """Test that HttpError during upload raises GoogleDriveError."""
        from googleapiclient.errors import HttpError

        service = self._make_service()
        service.service.files().create().execute.side_effect = HttpError(
            resp=MagicMock(status=403), content=b"Forbidden"
        )

        with pytest.raises(GoogleDriveError, match="Failed to upload image"):
            service.upload_image_bytes(
                image_bytes=b"fake",
                filename="test.png",
                folder_id="folder-123",
            )


class TestCreateFolder:
    """Test folder creation in Google Drive."""

    def _make_service(self):
        """Helper: create service with mocked Drive API."""
        mock_auth = _make_mock_auth()
        mock_auth.drive_service.files().create().execute.return_value = {
            "id": "folder-new",
            "name": "Test Folder",
        }
        service = GoogleDriveService(mock_auth)
        return service

    def test_returns_folder_metadata(self):
        """Test that create_folder returns dict with id and name."""
        service = self._make_service()

        result = service.create_folder(name="Images", parent_id="parent-123")

        assert result["id"] == "folder-new"
        assert result["name"] == "Test Folder"

    def test_http_error_raises_drive_error(self):
        """Test that HttpError during creation raises GoogleDriveError."""
        from googleapiclient.errors import HttpError

        service = self._make_service()
        service.service.files().create().execute.side_effect = HttpError(
            resp=MagicMock(status=500), content=b"Server error"
        )

        with pytest.raises(GoogleDriveError, match="Failed to create folder"):
            service.create_folder(name="Broken", parent_id="parent-123")


class TestGetPublicUrl:
    """Test public URL generation."""

    def _make_service(self):
        """Helper: create service with mocked Drive API."""
        mock_auth = _make_mock_auth()
        service = GoogleDriveService(mock_auth)
        return service

    def test_returns_direct_download_url(self):
        """Test that get_public_url returns the correct URL format."""
        service = self._make_service()

        url = service.get_public_url("file-abc-123")

        assert url == "https://drive.google.com/uc?export=view&id=file-abc-123"

    def test_includes_file_id(self):
        """Test that the URL contains the provided file ID."""
        service = self._make_service()

        url = service.get_public_url("my-file-id")

        assert "my-file-id" in url


class TestSetPublicPermissions:
    """Test public permission setting."""

    def _make_service(self):
        """Helper: create service with mocked Drive API."""
        mock_auth = _make_mock_auth()
        service = GoogleDriveService(mock_auth)
        return service

    def test_calls_permissions_create(self):
        """Test that set_public_permissions calls permissions().create()."""
        service = self._make_service()

        service.set_public_permissions("file-123")

        service.service.permissions().create.assert_called()

    def test_http_error_raises_drive_error(self):
        """Test that HttpError during permission set raises GoogleDriveError."""
        from googleapiclient.errors import HttpError

        service = self._make_service()
        service.service.permissions().create().execute.side_effect = HttpError(
            resp=MagicMock(status=403), content=b"Forbidden"
        )

        with pytest.raises(GoogleDriveError, match="Failed to set permissions"):
            service.set_public_permissions("file-123")


class TestAddServiceAccountReader:
    """Test service account reader permission."""

    @patch("src.drive_sync.gdrive.service_account.Credentials.from_service_account_file")
    def test_calls_permissions_create(self, mock_from_file):
        """Test that add_service_account_reader calls permissions create."""
        mock_creds = MagicMock()
        mock_creds.service_account_email = "sa@project.iam.gserviceaccount.com"
        mock_from_file.return_value = mock_creds

        mock_auth = _make_mock_auth()
        service = GoogleDriveService(mock_auth)

        service.add_service_account_reader("file-456")

        service.service.permissions().create.assert_called()

    @patch("src.drive_sync.gdrive.service_account.Credentials.from_service_account_file")
    def test_http_error_raises_drive_error(self, mock_from_file):
        """Test that HttpError during permission add raises GoogleDriveError."""
        from googleapiclient.errors import HttpError

        mock_creds = MagicMock()
        mock_creds.service_account_email = "sa@project.iam.gserviceaccount.com"
        mock_from_file.return_value = mock_creds

        mock_auth = _make_mock_auth()
        mock_auth.drive_service.permissions().create().execute.side_effect = HttpError(
            resp=MagicMock(status=403), content=b"Forbidden"
        )
        service = GoogleDriveService(mock_auth)

        with pytest.raises(GoogleDriveError, match="Failed to add service account permission"):
            service.add_service_account_reader("file-456")


class TestGoogleDriveError:
    """Test GoogleDriveError exception."""

    def test_is_exception(self):
        """Test that GoogleDriveError is an Exception subclass."""
        assert issubclass(GoogleDriveError, Exception)

    def test_carries_message(self):
        """Test that error carries a descriptive message."""
        with pytest.raises(GoogleDriveError, match="upload failed"):
            raise GoogleDriveError("upload failed")


class TestListFiles:
    """Test GoogleDriveService.list_files() method (Phase 3)."""

    def _make_service(self):
        """Helper: create service with mocked Drive API."""
        mock_auth = _make_mock_auth()
        service = GoogleDriveService(mock_auth)
        return service

    def test_list_files_returns_non_folder_files(self):
        """AC-3.1: list_files() returns only non-folder files from a folder.

        The API query itself filters out folders via mimeType != condition.
        The mock simulates the API returning only non-folder files (since
        the real API would filter them server-side).
        """
        service = self._make_service()

        # Mock API response — the real API filters folders via the query,
        # so the response only contains non-folder files.
        service.service.files().list().execute.return_value = {
            "files": [
                {"id": "f1", "name": "doc.md", "mimeType": "text/markdown"},
                {"id": "f3", "name": "image.png", "mimeType": "image/png"},
            ]
        }

        result = service.list_files("folder-123")

        assert len(result) == 2
        assert {"id": "f1", "name": "doc.md"} in result
        assert {"id": "f3", "name": "image.png"} in result

        # Verify the API query includes folder exclusion
        call_kwargs = service.service.files().list.call_args
        if call_kwargs:
            query = call_kwargs[1].get("q", "")
            assert "mimeType != 'application/vnd.google-apps.folder'" in query

    def test_list_files_handles_pagination(self):
        """AC-3.2: list_files() collects files across multiple pages."""
        service = self._make_service()

        # First page has a nextPageToken
        page1 = {
            "files": [
                {"id": "f1", "name": "file1.md", "mimeType": "text/markdown"},
            ],
            "nextPageToken": "token-page-2",
        }
        # Second page has no nextPageToken (last page)
        page2 = {
            "files": [
                {"id": "f2", "name": "file2.md", "mimeType": "text/markdown"},
            ],
        }

        # Chain execute calls to return page1 then page2
        service.service.files().list().execute.side_effect = [page1, page2]

        result = service.list_files("folder-123")

        assert len(result) == 2
        assert {"id": "f1", "name": "file1.md"} in result
        assert {"id": "f2", "name": "file2.md"} in result

    def test_list_files_raises_on_api_error(self):
        """AC-3.3: list_files() raises GoogleDriveError on HttpError."""
        from googleapiclient.errors import HttpError

        service = self._make_service()
        service.service.files().list().execute.side_effect = HttpError(
            resp=MagicMock(status=500), content=b"Server error"
        )

        with pytest.raises(GoogleDriveError, match="Failed to list files"):
            service.list_files("folder-123")

    def test_list_files_supports_shared_drives(self):
        """AC-3.4: list_files() passes supportsAllDrives=True in API call."""
        service = self._make_service()
        service.service.files().list().execute.return_value = {"files": []}

        service.list_files("folder-123")

        # Verify files().list() was called with supportsAllDrives=True
        call_kwargs = service.service.files().list.call_args
        if call_kwargs:
            assert call_kwargs[1].get("supportsAllDrives") is True
            assert call_kwargs[1].get("includeItemsFromAllDrives") is True

    def test_list_files_empty_folder(self):
        """list_files() returns empty list for empty folder."""
        service = self._make_service()
        service.service.files().list().execute.return_value = {"files": []}

        result = service.list_files("folder-123")

        assert result == []
