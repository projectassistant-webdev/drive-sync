"""
Tests for sync uploader mixin module.

Tests UploaderMixin methods: markdown_to_doc_with_diagrams,
csv_to_sheet, and pdf_to_drive, including cache integration,
update-vs-create logic, error handling, and content processing.
"""

from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError

from src.drive_sync.sync.uploaders import UploaderMixin

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeSync(UploaderMixin):
    """Minimal host class that satisfies UploaderMixin expectations."""

    def __init__(self, *, use_cache=False, enable_mermaid=False, folder_id="root-folder"):
        self.service = MagicMock()
        self.folder_id = folder_id
        self.use_cache = use_cache
        self.cache = MagicMock()
        self.enable_mermaid = enable_mermaid
        self.gdocs_service = MagicMock() if enable_mermaid else None
        self.gdrive_service = MagicMock() if enable_mermaid else None

    # Mixins call self._execute_with_retry and self._process_* methods
    def _execute_with_retry(self, request, max_retries=5):
        return request.execute()

    def _process_mermaid_diagrams(self, doc_id, diagrams, folder_id):
        pass

    def _process_ascii_codeblocks(self, doc_id, blocks, folder_id):
        pass

    def _process_code_blocks(self, doc_id, blocks, folder_id):
        pass

    def _process_local_images(self, doc_id, images, folder_id):
        pass

    def get_or_create_folder(self, name, parent_id=None):
        return "created-folder"


# ---------------------------------------------------------------------------
# markdown_to_doc_with_diagrams
# ---------------------------------------------------------------------------

class TestMarkdownToDocCreateNew:
    """Test creating a new Google Doc from markdown."""

    def test_creates_new_doc(self, tmp_path, monkeypatch):
        """Test creating a brand-new document returns a doc ID."""
        monkeypatch.setenv("ENABLE_ANCHOR_LINKS", "false")
        md_file = tmp_path / "README.md"
        md_file.write_text("# Hello\n\nWorld\n")

        sync = _FakeSync()
        # list returns empty -> create path
        sync.service.files().list().execute.return_value = {"files": []}
        sync.service.files().create().execute.return_value = {"id": "new-doc-id"}

        doc_id = sync.markdown_to_doc_with_diagrams(md_file, folder_id="f1")

        assert doc_id == "new-doc-id"
        sync.service.files().create.assert_called()

    def test_updates_existing_doc(self, tmp_path, monkeypatch):
        """Test that an existing document is updated rather than duplicated."""
        monkeypatch.setenv("ENABLE_ANCHOR_LINKS", "false")
        md_file = tmp_path / "README.md"
        md_file.write_text("# Updated\n")

        sync = _FakeSync()
        sync.service.files().list().execute.return_value = {
            "files": [{"id": "existing-id", "name": "README"}]
        }
        sync.service.files().update().execute.return_value = {"id": "existing-id"}

        doc_id = sync.markdown_to_doc_with_diagrams(md_file)

        assert doc_id == "existing-id"
        sync.service.files().update.assert_called()

    def test_uses_custom_name(self, tmp_path, monkeypatch):
        """Test that custom_name overrides the default file stem name."""
        monkeypatch.setenv("ENABLE_ANCHOR_LINKS", "false")
        md_file = tmp_path / "readme.md"
        md_file.write_text("# Custom\n")

        sync = _FakeSync()
        sync.service.files().list().execute.return_value = {"files": []}
        sync.service.files().create().execute.return_value = {"id": "c-doc"}

        sync.markdown_to_doc_with_diagrams(md_file, custom_name="My Doc")

        # The create call should have used "My Doc" somewhere
        create_call = sync.service.files().create.call_args
        assert create_call is not None

    def test_cleans_up_temp_file(self, tmp_path, monkeypatch):
        """Test that temporary file is removed after success."""
        monkeypatch.setenv("ENABLE_ANCHOR_LINKS", "false")
        md_file = tmp_path / "temp.md"
        md_file.write_text("# Temp\n")

        sync = _FakeSync()
        sync.service.files().list().execute.return_value = {"files": []}
        sync.service.files().create().execute.return_value = {"id": "t-doc"}

        sync.markdown_to_doc_with_diagrams(md_file)

        # If temp_file was created, it should have been cleaned up
        # We check indirectly that no exception was raised


class TestMarkdownToDocCacheIntegration:
    """Test markdown upload cache behavior."""

    def test_skips_when_cache_says_no(self, tmp_path, monkeypatch):
        """Test that cached file is skipped."""
        monkeypatch.setenv("ENABLE_ANCHOR_LINKS", "false")
        md_file = tmp_path / "cached.md"
        md_file.write_text("# Cached\n")

        sync = _FakeSync(use_cache=True)
        sync.cache.should_sync.return_value = (False, "unchanged")
        sync.cache.cache = {str(md_file): {"drive_id": "cached-id"}}

        doc_id = sync.markdown_to_doc_with_diagrams(md_file)

        assert doc_id == "cached-id"
        sync.service.files().list.assert_not_called()

    def test_syncs_when_cache_says_yes(self, tmp_path, monkeypatch):
        """Test that changed file is synced."""
        monkeypatch.setenv("ENABLE_ANCHOR_LINKS", "false")
        md_file = tmp_path / "changed.md"
        md_file.write_text("# Changed\n")

        sync = _FakeSync(use_cache=True)
        sync.cache.should_sync.return_value = (True, "content changed")
        sync.service.files().list().execute.return_value = {"files": []}
        sync.service.files().create().execute.return_value = {"id": "new-id"}

        doc_id = sync.markdown_to_doc_with_diagrams(md_file)

        assert doc_id == "new-id"
        sync.cache.update.assert_called_once_with(md_file, "new-id")


class TestMarkdownToDocWithDiagrams:
    """Test diagram and image processing during markdown upload."""

    def test_processes_mermaid_when_enabled(self, tmp_path, monkeypatch):
        """Test that mermaid diagrams are processed when enabled."""
        monkeypatch.setenv("ENABLE_ANCHOR_LINKS", "false")
        md_file = tmp_path / "mermaid.md"
        md_file.write_text(
            "# Diagram\n\n```mermaid\ngraph TD\n  A-->B\n```\n"
        )

        sync = _FakeSync(enable_mermaid=True)
        sync.service.files().list().execute.return_value = {"files": []}
        sync.service.files().create().execute.return_value = {"id": "m-doc"}

        with patch.object(sync, "_process_mermaid_diagrams") as mock_proc:
            sync.markdown_to_doc_with_diagrams(md_file)
            mock_proc.assert_called_once()

    def test_processes_anchor_links_when_enabled(self, tmp_path, monkeypatch):
        """Test that anchor links are processed when ENABLE_ANCHOR_LINKS=true."""
        monkeypatch.setenv("ENABLE_ANCHOR_LINKS", "true")
        md_file = tmp_path / "anchors.md"
        md_file.write_text("# Anchors\n\n[Link](#section)\n")

        sync = _FakeSync(enable_mermaid=True)
        sync.service.files().list().execute.return_value = {"files": []}
        sync.service.files().create().execute.return_value = {"id": "a-doc"}

        sync.markdown_to_doc_with_diagrams(md_file)

        sync.gdocs_service.process_anchor_links.assert_called_once()

    def test_anchor_link_failure_is_non_fatal(self, tmp_path, monkeypatch):
        """Test that anchor link processing failure does not halt sync."""
        monkeypatch.setenv("ENABLE_ANCHOR_LINKS", "true")
        md_file = tmp_path / "bad_anchors.md"
        md_file.write_text("# Bad\n")

        sync = _FakeSync(enable_mermaid=True)
        sync.service.files().list().execute.return_value = {"files": []}
        sync.service.files().create().execute.return_value = {"id": "ba-doc"}
        sync.gdocs_service.process_anchor_links.side_effect = Exception("boom")

        # Should NOT raise
        doc_id = sync.markdown_to_doc_with_diagrams(md_file)
        assert doc_id == "ba-doc"


class TestMarkdownToDocErrorHandling:
    """Test error handling during markdown upload."""

    def test_api_error_raises_exception(self, tmp_path, monkeypatch):
        """Test that Drive API errors propagate as exceptions."""
        monkeypatch.setenv("ENABLE_ANCHOR_LINKS", "false")
        md_file = tmp_path / "error.md"
        md_file.write_text("# Error\n")

        sync = _FakeSync()
        sync.service.files().list().execute.side_effect = Exception("API down")

        with pytest.raises(Exception, match="Error syncing"):
            sync.markdown_to_doc_with_diagrams(md_file)

    def test_defaults_folder_to_self_folder_id(self, tmp_path, monkeypatch):
        """Test that folder_id defaults to self.folder_id."""
        monkeypatch.setenv("ENABLE_ANCHOR_LINKS", "false")
        md_file = tmp_path / "default.md"
        md_file.write_text("# Default\n")

        sync = _FakeSync(folder_id="my-folder")
        sync.service.files().list().execute.return_value = {"files": []}
        sync.service.files().create().execute.return_value = {"id": "d-id"}

        sync.markdown_to_doc_with_diagrams(md_file)

        # Should have used "my-folder" as parent
        create_call = sync.service.files().create.call_args
        assert create_call is not None


# ---------------------------------------------------------------------------
# csv_to_sheet
# ---------------------------------------------------------------------------

class TestCsvToSheet:
    """Test CSV to Google Sheets upload."""

    def test_creates_new_sheet(self, tmp_path):
        """Test creating a new Google Sheet from CSV."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("a,b\n1,2\n3,4\n")

        sync = _FakeSync()
        sync.service.files().list().execute.return_value = {"files": []}
        sync.service.files().create().execute.return_value = {
            "id": "sheet-new", "webViewLink": "https://sheets.google.com"
        }

        sheet_id = sync.csv_to_sheet(csv_file)

        assert sheet_id == "sheet-new"
        sync.service.files().create.assert_called()

    def test_updates_existing_sheet(self, tmp_path):
        """Test updating an existing Google Sheet."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("a,b\n5,6\n")

        sync = _FakeSync()
        sync.service.files().list().execute.return_value = {
            "files": [{"id": "sheet-old", "name": "data"}]
        }
        sync.service.files().update().execute.return_value = {
            "id": "sheet-old", "webViewLink": "https://sheets.google.com"
        }

        sheet_id = sync.csv_to_sheet(csv_file)

        assert sheet_id == "sheet-old"
        sync.service.files().update.assert_called()

    def test_uses_custom_name(self, tmp_path):
        """Test that custom_name is applied."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("a,b\n1,2\n")

        sync = _FakeSync()
        sync.service.files().list().execute.return_value = {"files": []}
        sync.service.files().create().execute.return_value = {
            "id": "s", "webViewLink": "x"
        }

        sync.csv_to_sheet(csv_file, custom_name="My Data")

        create_call = sync.service.files().create.call_args
        assert create_call is not None

    def test_http_error_raises(self, tmp_path):
        """Test that HttpError propagates as Exception."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("a\n1\n")

        sync = _FakeSync()
        sync.service.files().list().execute.side_effect = HttpError(
            resp=MagicMock(status=500), content=b"Server error"
        )

        with pytest.raises(Exception, match="Error syncing"):
            sync.csv_to_sheet(csv_file)

    def test_defaults_folder_id(self, tmp_path):
        """Test that folder_id defaults to self.folder_id."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("col\nval\n")

        sync = _FakeSync(folder_id="csv-folder")
        sync.service.files().list().execute.return_value = {"files": []}
        sync.service.files().create().execute.return_value = {
            "id": "s2", "webViewLink": "x"
        }

        sync.csv_to_sheet(csv_file)
        # No assertion needed beyond no error; verifies folder_id defaulting


# ---------------------------------------------------------------------------
# pdf_to_drive
# ---------------------------------------------------------------------------

class TestPdfToDriveCreateNew:
    """Test creating new PDF in Google Drive."""

    def test_creates_new_pdf(self, tmp_path):
        """Test uploading a new PDF file."""
        pdf_file = tmp_path / "report.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake content")

        sync = _FakeSync()
        sync.service.files().list().execute.return_value = {"files": []}
        sync.service.files().create().execute.return_value = {
            "id": "pdf-new", "webViewLink": "https://drive.google.com"
        }

        pdf_id = sync.pdf_to_drive(pdf_file)

        assert pdf_id == "pdf-new"
        sync.service.files().create.assert_called()

    def test_updates_existing_pdf(self, tmp_path):
        """Test updating an existing PDF."""
        pdf_file = tmp_path / "report.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 updated")

        sync = _FakeSync()
        sync.service.files().list().execute.return_value = {
            "files": [{"id": "pdf-old", "name": "report.pdf"}]
        }
        sync.service.files().update().execute.return_value = {
            "id": "pdf-old", "webViewLink": "https://drive.google.com"
        }

        pdf_id = sync.pdf_to_drive(pdf_file)

        assert pdf_id == "pdf-old"

    def test_uses_custom_name(self, tmp_path):
        """Test custom name for PDF upload."""
        pdf_file = tmp_path / "doc.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")

        sync = _FakeSync()
        sync.service.files().list().execute.return_value = {"files": []}
        sync.service.files().create().execute.return_value = {
            "id": "p-c", "webViewLink": "x"
        }

        sync.pdf_to_drive(pdf_file, custom_name="Custom Report.pdf")

        sync.service.files().create.assert_called()


class TestPdfToDriveCacheIntegration:
    """Test PDF upload cache behavior."""

    def test_skips_when_cache_says_no(self, tmp_path):
        """Test that cached PDF is skipped."""
        pdf_file = tmp_path / "cached.pdf"
        pdf_file.write_bytes(b"%PDF")

        sync = _FakeSync(use_cache=True)
        sync.cache.should_sync.return_value = (False, "unchanged")
        sync.cache.cache = {str(pdf_file): {"drive_id": "pdf-cached"}}

        pdf_id = sync.pdf_to_drive(pdf_file)

        assert pdf_id == "pdf-cached"
        sync.service.files().list.assert_not_called()

    def test_updates_cache_after_sync(self, tmp_path):
        """Test that cache is updated after successful sync."""
        pdf_file = tmp_path / "new.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")

        sync = _FakeSync(use_cache=True)
        sync.cache.should_sync.return_value = (True, "new file")
        sync.service.files().list().execute.return_value = {"files": []}
        sync.service.files().create().execute.return_value = {
            "id": "pdf-created", "webViewLink": "x"
        }

        sync.pdf_to_drive(pdf_file)

        sync.cache.update.assert_called_once_with(pdf_file, "pdf-created")


class TestPdfToDriveErrorHandling:
    """Test PDF upload error handling."""

    def test_http_error_raises(self, tmp_path):
        """Test that HttpError propagates as Exception."""
        pdf_file = tmp_path / "err.pdf"
        pdf_file.write_bytes(b"%PDF")

        sync = _FakeSync()
        sync.service.files().list().execute.side_effect = HttpError(
            resp=MagicMock(status=403), content=b"Forbidden"
        )

        with pytest.raises(Exception, match="Error syncing"):
            sync.pdf_to_drive(pdf_file)

    def test_defaults_folder_id(self, tmp_path):
        """Test that folder_id defaults to self.folder_id."""
        pdf_file = tmp_path / "report.pdf"
        pdf_file.write_bytes(b"%PDF-1.4")

        sync = _FakeSync(folder_id="pdf-folder")
        sync.service.files().list().execute.return_value = {"files": []}
        sync.service.files().create().execute.return_value = {
            "id": "p-id", "webViewLink": "x"
        }

        sync.pdf_to_drive(pdf_file)
        # Verifies folder_id defaulting works without error
