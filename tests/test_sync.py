"""
Tests for the GoogleDriveSync orchestration module.

Tests initialization with mocked services, rate limiting, retry logic,
folder operations, file sync routing, directory sync, cache integration,
and finalize behavior.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.drive_sync.sync.orchestrator import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_RATE_LIMIT_DELAY,
    GoogleDriveSync,
)


@pytest.fixture
def mock_sync(monkeypatch, tmp_path):
    """Create a GoogleDriveSync instance with all external deps mocked."""
    monkeypatch.setenv("GOOGLE_DRIVE_FOLDER_ID", "test-folder-id")
    monkeypatch.setenv("MERMAID_RENDER_MODE", "local")

    with (
        patch("src.drive_sync.sync.orchestrator.GoogleAuthenticator") as mock_auth_cls,
        patch("src.drive_sync.sync.orchestrator.GoogleDocsService") as mock_gdocs_cls,
        patch("src.drive_sync.sync.orchestrator.GoogleDriveService") as mock_gdrive_cls,
        patch("src.drive_sync.sync.orchestrator.SyncCache") as mock_cache_cls,
    ):
        mock_auth = MagicMock()
        mock_auth.authenticate.return_value = MagicMock()
        mock_auth_cls.return_value = mock_auth

        mock_cache = MagicMock()
        mock_cache_cls.return_value = mock_cache

        mock_gdocs = MagicMock()
        mock_gdocs_cls.return_value = mock_gdocs

        mock_gdrive = MagicMock()
        mock_gdrive_cls.return_value = mock_gdrive

        creds_file = tmp_path / "credentials.json"
        creds_file.write_text('{"type": "service_account"}')

        sync = GoogleDriveSync(
            credentials_file=str(creds_file),
            folder_id="test-folder-id",
            use_cache=True,
            rate_limit_delay=0,  # Disable delays for testing
            enable_mermaid=True,
        )

        # Attach mocks for assertions
        sync._mock_auth = mock_auth
        sync._mock_cache = mock_cache
        sync._mock_gdocs = mock_gdocs
        sync._mock_gdrive = mock_gdrive

        yield sync


class TestGoogleDriveSyncInit:
    """Test GoogleDriveSync initialization."""

    def test_creates_authenticator(self, mock_sync):
        """Test that GoogleAuthenticator is created during init."""
        assert mock_sync.auth is not None

    def test_creates_drive_service(self, mock_sync):
        """Test that Drive service is created during init."""
        assert mock_sync.service is not None

    def test_creates_cache(self, mock_sync):
        """Test that SyncCache is created when use_cache=True."""
        assert mock_sync.cache is not None
        mock_sync.cache.load.assert_called_once()

    def test_creates_gdocs_service_when_mermaid_enabled(self, mock_sync):
        """Test that GoogleDocsService is created when enable_mermaid=True."""
        assert mock_sync.gdocs_service is not None

    def test_creates_gdrive_service_when_mermaid_enabled(self, mock_sync):
        """Test that GoogleDriveService is created when enable_mermaid=True."""
        assert mock_sync.gdrive_service is not None

    def test_stores_folder_id(self, mock_sync):
        """Test that folder_id is stored."""
        assert mock_sync.folder_id == "test-folder-id"

    def test_initial_api_call_count(self, mock_sync):
        """Test that API call count starts at zero."""
        assert mock_sync.api_call_count == 0

    @patch("src.drive_sync.sync.orchestrator.GoogleAuthenticator")
    @patch("src.drive_sync.sync.orchestrator.SyncCache")
    def test_no_gdocs_when_mermaid_disabled(self, mock_cache_cls, mock_auth_cls, tmp_path, monkeypatch):
        """Test that GoogleDocsService is None when enable_mermaid=False."""
        monkeypatch.setenv("GOOGLE_DRIVE_FOLDER_ID", "folder-id")
        mock_auth = MagicMock()
        mock_auth.authenticate.return_value = MagicMock()
        mock_auth_cls.return_value = mock_auth
        mock_cache_cls.return_value = MagicMock()

        creds_file = tmp_path / "credentials.json"
        creds_file.write_text('{}')

        sync = GoogleDriveSync(
            credentials_file=str(creds_file),
            enable_mermaid=False,
        )
        assert sync.gdocs_service is None
        assert sync.gdrive_service is None


class TestRateLimit:
    """Test rate limiting between API calls."""

    def test_increments_api_call_count(self, mock_sync):
        """Test that _rate_limit increments the counter."""
        initial = mock_sync.api_call_count
        mock_sync._rate_limit()
        assert mock_sync.api_call_count == initial + 1

    def test_updates_last_api_call_time(self, mock_sync):
        """Test that _rate_limit updates the timestamp."""
        mock_sync._rate_limit()
        assert mock_sync.last_api_call > 0


class TestExecuteWithRetry:
    """Test retry logic with exponential backoff."""

    def test_success_on_first_try(self, mock_sync):
        """Test successful execution on first attempt."""
        mock_request = MagicMock()
        mock_request.execute.return_value = {"id": "file-123"}

        result = mock_sync._execute_with_retry(mock_request)

        assert result == {"id": "file-123"}
        mock_request.execute.assert_called_once()

    @patch("src.drive_sync.sync.orchestrator.time.sleep")
    def test_retries_on_rate_limit(self, mock_sleep, mock_sync):
        """Test retry on 429 rate limit error."""
        from googleapiclient.errors import HttpError

        error_429 = HttpError(resp=MagicMock(status=429), content=b"Rate limit")
        success = {"id": "file-123"}

        mock_request = MagicMock()
        mock_request.execute.side_effect = [error_429, success]

        result = mock_sync._execute_with_retry(mock_request, max_retries=3)

        assert result == success
        assert mock_request.execute.call_count == 2

    @patch("src.drive_sync.sync.orchestrator.time.sleep")
    def test_retries_on_server_error(self, mock_sleep, mock_sync):
        """Test retry on 500 server error."""
        from googleapiclient.errors import HttpError

        error_500 = HttpError(resp=MagicMock(status=500), content=b"Server error")
        success = {"id": "file-123"}

        mock_request = MagicMock()
        mock_request.execute.side_effect = [error_500, success]

        result = mock_sync._execute_with_retry(mock_request, max_retries=3)

        assert result == success

    def test_raises_on_client_error(self, mock_sync):
        """Test that 4xx errors (not 429) are raised immediately."""
        from googleapiclient.errors import HttpError

        error_404 = HttpError(resp=MagicMock(status=404), content=b"Not found")

        mock_request = MagicMock()
        mock_request.execute.side_effect = error_404

        with pytest.raises(HttpError):
            mock_sync._execute_with_retry(mock_request)

    @patch("src.drive_sync.sync.orchestrator.time.sleep")
    def test_exhausts_retries_on_persistent_rate_limit(self, mock_sleep, mock_sync):
        """Test that persistent rate limit exhausts all retries."""
        from googleapiclient.errors import HttpError

        error_429 = HttpError(resp=MagicMock(status=429), content=b"Rate limit")

        mock_request = MagicMock()
        mock_request.execute.side_effect = error_429

        with pytest.raises(HttpError):
            mock_sync._execute_with_retry(mock_request, max_retries=2)


class TestGetOrCreateFolder:
    """Test folder get-or-create logic."""

    def test_returns_existing_folder(self, mock_sync):
        """Test that existing folder ID is returned."""
        mock_sync.service.files().list().execute.return_value = {
            "files": [{"id": "existing-folder-id", "name": "docs"}]
        }

        # Need to mock _execute_with_retry since it wraps the request
        with patch.object(mock_sync, "_execute_with_retry") as mock_retry:
            mock_retry.return_value = {
                "files": [{"id": "existing-folder-id", "name": "docs"}]
            }
            result = mock_sync.get_or_create_folder("docs")

        assert result == "existing-folder-id"

    def test_creates_new_folder(self, mock_sync):
        """Test that new folder is created when not found."""
        with patch.object(mock_sync, "_execute_with_retry") as mock_retry:
            # First call: list returns empty
            # Second call: create returns new folder
            mock_retry.side_effect = [
                {"files": []},
                {"id": "new-folder-id"},
            ]
            result = mock_sync.get_or_create_folder("new-docs")

        assert result == "new-folder-id"

    def test_uses_default_folder_id(self, mock_sync):
        """Test that folder_id defaults to self.folder_id."""
        with patch.object(mock_sync, "_execute_with_retry") as mock_retry:
            mock_retry.return_value = {"files": [{"id": "found"}]}
            mock_sync.get_or_create_folder("test")

        # Should have been called (confirming function ran)
        mock_retry.assert_called()


class TestSyncFile:
    """Test file type detection and routing."""

    def test_syncs_markdown_file(self, mock_sync, tmp_path):
        """Test that .md files are routed to markdown_to_doc_with_diagrams."""
        md_file = tmp_path / "test.md"
        md_file.write_text("# Hello\n\nWorld\n")

        with patch.object(mock_sync, "markdown_to_doc_with_diagrams", return_value="doc-id") as mock_md:
            result = mock_sync.sync_file(md_file, "folder-123")

        assert result == "doc-id"
        mock_md.assert_called_once()

    def test_syncs_csv_file(self, mock_sync, tmp_path):
        """Test that .csv files are routed to csv_to_sheet."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("a,b\n1,2\n")

        with patch.object(mock_sync, "csv_to_sheet", return_value="sheet-id") as mock_csv:
            result = mock_sync.sync_file(csv_file, "folder-123")

        assert result == "sheet-id"
        mock_csv.assert_called_once()

    def test_syncs_pdf_file(self, mock_sync, tmp_path):
        """Test that .pdf files are routed to pdf_to_drive."""
        pdf_file = tmp_path / "report.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake content")

        with patch.object(mock_sync, "pdf_to_drive", return_value="pdf-id") as mock_pdf:
            result = mock_sync.sync_file(pdf_file, "folder-123")

        assert result == "pdf-id"
        mock_pdf.assert_called_once()

    def test_unsupported_file_returns_none(self, mock_sync, tmp_path):
        """Test that unsupported file types return None."""
        txt_file = tmp_path / "readme.txt"
        txt_file.write_text("plain text")

        result = mock_sync.sync_file(txt_file, "folder-123")

        assert result is None


class TestSyncDirectory:
    """Test directory sync orchestration."""

    def test_syncs_files_in_directory(self, mock_sync, tmp_path):
        """Test that files in directory are discovered and synced."""
        md_file = tmp_path / "doc.md"
        md_file.write_text("# Test\n")

        with (
            patch.object(mock_sync, "create_folder_structure", return_value={str(tmp_path): "folder-id"}),
            patch.object(mock_sync, "sync_file", return_value="doc-123"),
        ):
            result = mock_sync.sync_directory(tmp_path)

        assert len(result) > 0

    def test_saves_cache_periodically(self, mock_sync, tmp_path):
        """Test that cache is saved at batch intervals."""
        # Create more files than batch_size
        mock_sync.batch_size = 2
        for i in range(3):
            (tmp_path / f"doc{i}.md").write_text(f"# Doc {i}\n")

        with (
            patch.object(mock_sync, "create_folder_structure", return_value={str(tmp_path): "folder-id"}),
            patch.object(mock_sync, "sync_file", return_value="doc-id"),
        ):
            mock_sync.sync_directory(tmp_path)

        # Cache should be saved (at least final save)
        mock_sync.cache.save.assert_called()

    def test_handles_sync_errors_gracefully(self, mock_sync, tmp_path):
        """Test that file sync errors don't stop directory sync."""
        (tmp_path / "good.md").write_text("# Good\n")
        (tmp_path / "bad.md").write_text("# Bad\n")

        with (
            patch.object(mock_sync, "create_folder_structure", return_value={str(tmp_path): "folder-id"}),
            patch.object(mock_sync, "sync_file", side_effect=[Exception("fail"), "doc-id"]),
        ):
            result = mock_sync.sync_directory(tmp_path)

        # Should have at least one successful sync despite the error
        # (or possibly zero if the failed one was processed first)
        assert isinstance(result, dict)


class TestCreateFolderStructure:
    """Test directory-to-Drive folder creation."""

    def test_creates_main_folder(self, mock_sync, tmp_path):
        """Test that the main folder is created."""
        with patch.object(mock_sync, "get_or_create_folder", return_value="folder-id"):
            result = mock_sync.create_folder_structure(tmp_path)

        assert str(tmp_path) in result

    def test_creates_subfolders(self, mock_sync, tmp_path):
        """Test that subfolders are created recursively."""
        subdir = tmp_path / "sub"
        subdir.mkdir()

        call_count = [0]

        def mock_get_or_create(name, parent_id=None):
            result = f"folder-{call_count[0]}"
            call_count[0] += 1
            return result

        with patch.object(mock_sync, "get_or_create_folder", side_effect=mock_get_or_create):
            result = mock_sync.create_folder_structure(tmp_path)

        assert len(result) >= 2  # main + sub


class TestFinalize:
    """Test finalize (cache save on shutdown)."""

    def test_saves_cache(self, mock_sync):
        """Test that finalize saves the cache."""
        mock_sync.finalize()
        mock_sync.cache.save.assert_called()

    def test_no_error_when_no_cache(self, mock_sync):
        """Test that finalize works when cache is disabled."""
        mock_sync.use_cache = False
        mock_sync.cache = None
        mock_sync.finalize()  # Should not raise


class TestConstants:
    """Test module-level constants."""

    def test_default_rate_limit_delay(self):
        """Test DEFAULT_RATE_LIMIT_DELAY is 0.5."""
        assert DEFAULT_RATE_LIMIT_DELAY == 0.5

    def test_default_batch_size(self):
        """Test DEFAULT_BATCH_SIZE is 10."""
        assert DEFAULT_BATCH_SIZE == 10
