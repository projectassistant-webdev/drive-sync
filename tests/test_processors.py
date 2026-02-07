"""
Tests for sync processor mixin module.

Tests helper functions (_find_text_marker, _upload_and_get_url) and
ProcessorMixin methods for Mermaid diagrams, ASCII codeblocks,
syntax-highlighted code blocks, and local images.
"""

from unittest.mock import MagicMock, patch

from src.drive_sync.sync.processors import (
    ProcessorMixin,
    _find_text_marker,
    _upload_and_get_url,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeSync(ProcessorMixin):
    """Minimal host class that satisfies ProcessorMixin expectations."""

    def __init__(self):
        self.gdocs_service = MagicMock()
        self.gdrive_service = MagicMock()

    def get_or_create_folder(self, name, parent_id=None):
        return "folder-img-id"


def _doc_with_text(text, start_index=0):
    """Build a minimal Google Doc structure containing *text*."""
    return {
        "body": {
            "content": [{
                "paragraph": {
                    "elements": [{
                        "textRun": {"content": text},
                        "startIndex": start_index,
                    }]
                }
            }]
        }
    }


# ---------------------------------------------------------------------------
# _find_text_marker
# ---------------------------------------------------------------------------

class TestFindTextMarker:
    """Test _find_text_marker helper function."""

    def test_finds_marker_at_start(self):
        """Test finding marker at the beginning of text."""
        gdocs = MagicMock()
        gdocs.docs_service.documents().get().execute.return_value = (
            _doc_with_text("[ASCII:wireframe]", start_index=10)
        )
        idx = _find_text_marker(gdocs, "doc-1", "[ASCII:wireframe]")
        assert idx == 10

    def test_finds_marker_in_middle(self):
        """Test finding marker embedded in surrounding text."""
        gdocs = MagicMock()
        gdocs.docs_service.documents().get().execute.return_value = (
            _doc_with_text("Before [ASCII:wire] After", start_index=5)
        )
        idx = _find_text_marker(gdocs, "doc-1", "[ASCII:wire]")
        assert idx == 5 + "Before [ASCII:wire] After".find("[ASCII:wire]")

    def test_returns_none_when_not_found(self):
        """Test that None is returned when marker does not exist."""
        gdocs = MagicMock()
        gdocs.docs_service.documents().get().execute.return_value = (
            _doc_with_text("no markers here")
        )
        assert _find_text_marker(gdocs, "doc-1", "[ASCII:missing]") is None

    def test_returns_none_on_empty_doc(self):
        """Test that None is returned for empty document."""
        gdocs = MagicMock()
        gdocs.docs_service.documents().get().execute.return_value = {
            "body": {"content": []}
        }
        assert _find_text_marker(gdocs, "doc-1", "[ASCII:test]") is None

    def test_handles_element_without_textrun(self):
        """Test that elements without textRun are skipped."""
        gdocs = MagicMock()
        gdocs.docs_service.documents().get().execute.return_value = {
            "body": {
                "content": [{
                    "paragraph": {
                        "elements": [{"inlineObjectElement": {"inlineObjectId": "obj1"}}]
                    }
                }]
            }
        }
        assert _find_text_marker(gdocs, "doc-1", "[ASCII:test]") is None


# ---------------------------------------------------------------------------
# _upload_and_get_url
# ---------------------------------------------------------------------------

class TestUploadAndGetUrl:
    """Test _upload_and_get_url helper function."""

    @patch("src.drive_sync.sync.processors.time.sleep")
    def test_returns_public_url(self, mock_sleep):
        """Test that a public Drive URL is returned."""
        gdrive = MagicMock()
        gdrive.upload_image_bytes.return_value = {"id": "img-123"}

        url = _upload_and_get_url(
            gdrive, lambda n, fid: "folder-created",
            b"\x89PNG", "diagram1", "parent-folder", {}, delay=0
        )

        assert url == "https://drive.google.com/uc?export=view&id=img-123"
        gdrive.upload_image_bytes.assert_called_once()
        gdrive.set_public_permissions.assert_called_once_with("img-123")

    @patch("src.drive_sync.sync.processors.time.sleep")
    def test_caches_folder_id(self, mock_sleep):
        """Test that folder ID is cached after first creation."""
        gdrive = MagicMock()
        gdrive.upload_image_bytes.return_value = {"id": "img-1"}
        cache = {}

        _upload_and_get_url(
            gdrive, lambda n, fid: "new-folder", b"\x89PNG",
            "d1", "parent", cache, delay=0
        )
        assert cache["id"] == "new-folder"

        # Second call should reuse cached folder
        mock_create_folder = MagicMock(return_value="should-not-be-called")
        _upload_and_get_url(
            gdrive, mock_create_folder, b"\x89PNG",
            "d2", "parent", cache, delay=0
        )
        mock_create_folder.assert_not_called()

    @patch("src.drive_sync.sync.processors.time.sleep")
    def test_permissions_failure_logged_not_raised(self, mock_sleep):
        """Test that permission errors are logged but don't raise."""
        gdrive = MagicMock()
        gdrive.upload_image_bytes.return_value = {"id": "img-x"}
        gdrive.set_public_permissions.side_effect = Exception("perm error")

        # Should NOT raise
        url = _upload_and_get_url(
            gdrive, lambda n, fid: "folder", b"\x89PNG",
            "d", "p", {}, delay=0
        )
        assert "img-x" in url


# ---------------------------------------------------------------------------
# ProcessorMixin._process_mermaid_diagrams
# ---------------------------------------------------------------------------

class TestProcessMermaidDiagrams:
    """Test ProcessorMixin._process_mermaid_diagrams."""

    @patch("src.drive_sync.sync.processors.render_mermaid_diagram", return_value=b"\x89PNG")
    @patch("src.drive_sync.sync.processors._upload_and_get_url",
           return_value="https://drive.google.com/uc?export=view&id=x")
    def test_local_mode_uploads_to_drive(self, mock_upload, mock_render, monkeypatch):
        """Test that local render mode renders and uploads to Drive."""
        monkeypatch.setenv("MERMAID_RENDER_MODE", "local")
        sync = _FakeSync()
        sync.gdocs_service.find_diagram_markers.return_value = [
            {"name": "flow", "index": 10, "length": 15}
        ]

        sync._process_mermaid_diagrams(
            "doc-1",
            [{"name": "flow", "code": "graph TD\n  A-->B"}],
            "folder-1",
        )

        mock_render.assert_called_once()
        mock_upload.assert_called_once()
        sync.gdocs_service.embed_diagram.assert_called_once()

    @patch("src.drive_sync.sync.processors.get_mermaid_url",
           return_value="https://mermaid.ink/img/short")
    def test_api_mode_uses_direct_url(self, mock_url, monkeypatch):
        """Test that API mode uses direct Mermaid URL when short enough."""
        monkeypatch.setenv("MERMAID_RENDER_MODE", "api")
        sync = _FakeSync()
        sync.gdocs_service.find_diagram_markers.return_value = [
            {"name": "flow", "index": 0, "length": 15}
        ]

        sync._process_mermaid_diagrams(
            "doc-1",
            [{"name": "flow", "code": "graph TD\n  A-->B"}],
            "folder-1",
        )

        mock_url.assert_called_once()
        sync.gdocs_service.embed_diagram.assert_called_once()

    @patch("src.drive_sync.sync.processors.render_mermaid_diagram",
           side_effect=Exception("render boom"))
    def test_render_error_is_caught(self, mock_render, monkeypatch):
        """Test that render errors are caught and logged."""
        monkeypatch.setenv("MERMAID_RENDER_MODE", "local")
        sync = _FakeSync()

        # Should NOT raise
        sync._process_mermaid_diagrams(
            "doc-1",
            [{"name": "bad", "code": "invalid"}],
            "folder-1",
        )
        sync.gdocs_service.embed_diagram.assert_not_called()

    @patch("src.drive_sync.sync.processors.render_mermaid_diagram", return_value=b"\x89PNG")
    @patch("src.drive_sync.sync.processors._upload_and_get_url",
           return_value="https://drive.google.com/uc?export=view&id=x")
    def test_marker_not_found_skips_embed(self, mock_upload, mock_render, monkeypatch):
        """Test that missing marker skips embedding."""
        monkeypatch.setenv("MERMAID_RENDER_MODE", "local")
        sync = _FakeSync()
        sync.gdocs_service.find_diagram_markers.return_value = []

        sync._process_mermaid_diagrams(
            "doc-1",
            [{"name": "missing", "code": "graph TD\n  A-->B"}],
            "folder-1",
        )

        sync.gdocs_service.embed_diagram.assert_not_called()


# ---------------------------------------------------------------------------
# ProcessorMixin._process_ascii_codeblocks
# ---------------------------------------------------------------------------

class TestProcessAsciiCodeblocks:
    """Test ProcessorMixin._process_ascii_codeblocks."""

    @patch("src.drive_sync.sync.processors._find_text_marker", return_value=42)
    @patch("src.drive_sync.sync.processors._upload_and_get_url",
           return_value="https://drive.google.com/uc?export=view&id=ascii-1")
    @patch("src.drive_sync.sync.processors.render_ascii_to_image", return_value=b"\x89PNG")
    def test_renders_and_embeds(self, mock_render, mock_upload, mock_marker):
        """Test successful ASCII block render and embed."""
        sync = _FakeSync()

        sync._process_ascii_codeblocks(
            "doc-1",
            [{"name": "wire", "code": "+---------+\n| Hello   |\n+---------+"}],
            "folder-1",
        )

        mock_render.assert_called_once()
        mock_upload.assert_called_once()
        sync.gdocs_service.embed_diagram.assert_called_once()

    @patch("src.drive_sync.sync.processors._find_text_marker", return_value=None)
    @patch("src.drive_sync.sync.processors._upload_and_get_url",
           return_value="https://drive.google.com/uc?export=view&id=a")
    @patch("src.drive_sync.sync.processors.render_ascii_to_image", return_value=b"\x89PNG")
    def test_marker_not_found_skips_embed(self, mock_render, mock_upload, mock_marker):
        """Test that missing marker skips embedding."""
        sync = _FakeSync()

        sync._process_ascii_codeblocks(
            "doc-1",
            [{"name": "wire", "code": "box art"}],
            "folder-1",
        )

        sync.gdocs_service.embed_diagram.assert_not_called()

    @patch("src.drive_sync.sync.processors.render_ascii_to_image",
           side_effect=Exception("render fail"))
    def test_render_error_is_caught(self, mock_render):
        """Test that render errors are caught gracefully."""
        sync = _FakeSync()

        sync._process_ascii_codeblocks(
            "doc-1",
            [{"name": "bad", "code": "x"}],
            "folder-1",
        )
        sync.gdocs_service.embed_diagram.assert_not_called()


# ---------------------------------------------------------------------------
# ProcessorMixin._process_code_blocks
# ---------------------------------------------------------------------------

class TestProcessCodeBlocks:
    """Test ProcessorMixin._process_code_blocks."""

    @patch("src.drive_sync.sync.processors._find_text_marker", return_value=100)
    @patch("src.drive_sync.sync.processors._upload_and_get_url",
           return_value="https://drive.google.com/uc?export=view&id=code-1")
    @patch("src.drive_sync.sync.processors.render_code_to_image", return_value=b"\x89PNG")
    def test_renders_and_embeds(self, mock_render, mock_upload, mock_marker):
        """Test successful code block render and embed."""
        sync = _FakeSync()

        sync._process_code_blocks(
            "doc-1",
            [{"name": "snippet", "code": "print('hello')", "language": "python"}],
            "folder-1",
        )

        mock_render.assert_called_once()
        mock_upload.assert_called_once()
        sync.gdocs_service.embed_diagram.assert_called_once()

    @patch("src.drive_sync.sync.processors._find_text_marker", return_value=None)
    @patch("src.drive_sync.sync.processors._upload_and_get_url",
           return_value="https://drive.google.com/uc?export=view&id=c")
    @patch("src.drive_sync.sync.processors.render_code_to_image", return_value=b"\x89PNG")
    def test_marker_not_found_skips_embed(self, mock_render, mock_upload, mock_marker):
        """Test that missing marker skips embedding."""
        sync = _FakeSync()

        sync._process_code_blocks(
            "doc-1",
            [{"name": "code1", "code": "x=1", "language": "python"}],
            "folder-1",
        )

        sync.gdocs_service.embed_diagram.assert_not_called()

    @patch("src.drive_sync.sync.processors.render_code_to_image",
           side_effect=Exception("render fail"))
    def test_render_error_is_caught(self, mock_render):
        """Test that render errors are caught gracefully."""
        sync = _FakeSync()

        sync._process_code_blocks(
            "doc-1",
            [{"name": "bad", "code": "x", "language": "py"}],
            "folder-1",
        )
        sync.gdocs_service.embed_diagram.assert_not_called()

    @patch("src.drive_sync.sync.processors._find_text_marker", return_value=5)
    @patch("src.drive_sync.sync.processors._upload_and_get_url",
           return_value="https://drive.google.com/uc?export=view&id=c2")
    @patch("src.drive_sync.sync.processors.render_code_to_image", return_value=b"\x89PNG")
    def test_missing_language_defaults_to_empty(self, mock_render, mock_upload, mock_marker):
        """Test that missing language key defaults to empty string."""
        sync = _FakeSync()

        sync._process_code_blocks(
            "doc-1",
            [{"name": "snippet2", "code": "x=1"}],
            "folder-1",
        )

        # render_code_to_image should be called with language=''
        render_kwargs = mock_render.call_args
        assert render_kwargs[1]["language"] == ""


# ---------------------------------------------------------------------------
# ProcessorMixin._process_local_images
# ---------------------------------------------------------------------------

class TestProcessLocalImages:
    """Test ProcessorMixin._process_local_images."""

    def test_uploads_and_embeds_existing_image(self, tmp_path):
        """Test uploading and embedding an existing local image."""
        img = tmp_path / "photo.png"
        img.write_bytes(b"\x89PNG" + b"\x00" * 50)

        sync = _FakeSync()
        sync.gdrive_service.upload_image_bytes.return_value = {"id": "img-99"}
        # Simulate _find_image_markers returning matching marker
        sync.gdocs_service.docs_service.documents().get().execute.return_value = {
            "body": {
                "content": [{
                    "paragraph": {
                        "elements": [{
                            "textRun": {"content": "[IMAGE:photo_marker]"},
                            "startIndex": 0,
                        }]
                    }
                }]
            }
        }

        images = [{
            "name": "photo_marker",
            "path": str(img),
            "display_name": "photo",
        }]

        sync._process_local_images("doc-1", images, "folder-1")

        sync.gdrive_service.upload_image_bytes.assert_called_once()
        sync.gdrive_service.add_service_account_reader.assert_called_once_with("img-99")

    def test_skips_missing_image_file(self, tmp_path):
        """Test that missing image file is skipped."""
        sync = _FakeSync()

        images = [{
            "name": "missing_marker",
            "path": str(tmp_path / "nonexistent.png"),
            "display_name": "missing",
        }]

        sync._process_local_images("doc-1", images, "folder-1")

        sync.gdrive_service.upload_image_bytes.assert_not_called()

    def test_handles_upload_exception(self, tmp_path):
        """Test that upload exceptions are caught."""
        img = tmp_path / "bad.png"
        img.write_bytes(b"\x89PNG" + b"\x00" * 10)

        sync = _FakeSync()
        sync.gdrive_service.upload_image_bytes.side_effect = Exception("upload boom")

        images = [{
            "name": "bad_marker",
            "path": str(img),
            "display_name": "bad",
        }]

        # Should NOT raise
        sync._process_local_images("doc-1", images, "folder-1")

    def test_permission_errors_are_non_fatal(self, tmp_path):
        """Test that permission setting errors do not stop processing."""
        img = tmp_path / "ok.jpg"
        img.write_bytes(b"\xFF\xD8" + b"\x00" * 10)

        sync = _FakeSync()
        sync.gdrive_service.upload_image_bytes.return_value = {"id": "img-77"}
        sync.gdrive_service.add_service_account_reader.side_effect = Exception("perm err")
        sync.gdrive_service.set_public_permissions.side_effect = Exception("perm err 2")

        # Need marker to exist
        sync.gdocs_service.docs_service.documents().get().execute.return_value = {
            "body": {
                "content": [{
                    "paragraph": {
                        "elements": [{
                            "textRun": {"content": "[IMAGE:img_marker]"},
                            "startIndex": 0,
                        }]
                    }
                }]
            }
        }

        images = [{
            "name": "img_marker",
            "path": str(img),
            "display_name": "ok",
        }]

        # Should NOT raise
        sync._process_local_images("doc-1", images, "folder-1")
        sync.gdocs_service.embed_diagram.assert_called_once()

    def test_detects_jpeg_mime_type(self, tmp_path):
        """Test that JPEG files get correct MIME type."""
        img = tmp_path / "photo.jpeg"
        img.write_bytes(b"\xFF\xD8" + b"\x00" * 10)

        sync = _FakeSync()
        sync.gdrive_service.upload_image_bytes.return_value = {"id": "img-j"}

        # No marker match to keep test focused
        sync.gdocs_service.docs_service.documents().get().execute.return_value = {
            "body": {"content": []}
        }

        images = [{
            "name": "jpeg_marker",
            "path": str(img),
            "display_name": "photo",
        }]

        sync._process_local_images("doc-1", images, "folder-1")

        upload_call = sync.gdrive_service.upload_image_bytes.call_args
        assert upload_call[1]["mime_type"] == "image/jpeg"


# ---------------------------------------------------------------------------
# ProcessorMixin._find_image_markers
# ---------------------------------------------------------------------------

class TestFindImageMarkers:
    """Test ProcessorMixin._find_image_markers."""

    def test_finds_single_marker(self):
        """Test finding a single image marker."""
        sync = _FakeSync()
        sync.gdocs_service.docs_service.documents().get().execute.return_value = {
            "body": {
                "content": [{
                    "paragraph": {
                        "elements": [{
                            "textRun": {"content": "Before [IMAGE:photo1] After"},
                            "startIndex": 0,
                        }]
                    }
                }]
            }
        }

        markers = sync._find_image_markers("doc-1")

        assert len(markers) == 1
        assert markers[0]["name"] == "photo1"
        assert markers[0]["length"] == len("[IMAGE:photo1]")

    def test_finds_multiple_markers(self):
        """Test finding multiple image markers."""
        sync = _FakeSync()
        sync.gdocs_service.docs_service.documents().get().execute.return_value = {
            "body": {
                "content": [
                    {
                        "paragraph": {
                            "elements": [{
                                "textRun": {"content": "[IMAGE:img1]"},
                                "startIndex": 0,
                            }]
                        }
                    },
                    {
                        "paragraph": {
                            "elements": [{
                                "textRun": {"content": "[IMAGE:img2]"},
                                "startIndex": 50,
                            }]
                        }
                    },
                ]
            }
        }

        markers = sync._find_image_markers("doc-1")
        assert len(markers) == 2
        assert markers[0]["name"] == "img1"
        assert markers[1]["name"] == "img2"

    def test_returns_empty_on_no_markers(self):
        """Test that empty list is returned when no markers exist."""
        sync = _FakeSync()
        sync.gdocs_service.docs_service.documents().get().execute.return_value = {
            "body": {"content": [{"paragraph": {"elements": [
                {"textRun": {"content": "plain text"}, "startIndex": 0}
            ]}}]}
        }

        assert sync._find_image_markers("doc-1") == []

    def test_returns_empty_on_error(self):
        """Test that errors return empty list."""
        sync = _FakeSync()
        sync.gdocs_service.docs_service.documents().get().execute.side_effect = Exception("API fail")

        assert sync._find_image_markers("doc-1") == []

    def test_returns_empty_on_empty_doc(self):
        """Test with empty document content."""
        sync = _FakeSync()
        sync.gdocs_service.docs_service.documents().get().execute.return_value = {
            "body": {"content": []}
        }

        assert sync._find_image_markers("doc-1") == []
