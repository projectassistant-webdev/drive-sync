"""
Tests for Google Docs service module.

Tests GoogleDocsService initialization (shared auth and legacy),
diagram marker detection, diagram embedding, heading parsing,
anchor link discovery, anchor link conversion, and error handling.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.drive_sync.auth import GoogleAuthenticator
from src.drive_sync.gdocs import GoogleDocsError, GoogleDocsService


def _make_mock_auth():
    """Create a mock GoogleAuthenticator that passes isinstance checks.

    GoogleDocsService.__init__ uses ``isinstance(arg, GoogleAuthenticator)``
    to decide the init path, so we need a proper spec-based mock.
    """
    mock_auth = MagicMock(spec=GoogleAuthenticator)
    mock_auth.credentials_file = Path("credentials.json")
    mock_auth.docs_service = MagicMock()
    mock_auth.drive_service = MagicMock()
    return mock_auth


class TestGoogleDocsServiceInit:
    """Test GoogleDocsService initialization modes."""

    def test_init_with_shared_authenticator(self):
        """Test initialization with a GoogleAuthenticator instance."""
        mock_auth = _make_mock_auth()
        service = GoogleDocsService(mock_auth)

        assert service.docs_service == mock_auth.docs_service
        assert service.drive_service == mock_auth.drive_service
        assert service.credentials_path == "credentials.json"

    @patch("src.drive_sync.gdocs.build")
    @patch("src.drive_sync.gdocs.service_account.Credentials.from_service_account_file")
    def test_init_with_legacy_path(self, mock_from_file, mock_build, tmp_path):
        """Test initialization with credentials file path string."""
        creds_file = tmp_path / "credentials.json"
        creds_file.write_text('{"type": "service_account"}')

        mock_from_file.return_value = MagicMock()
        mock_build.return_value = MagicMock()

        service = GoogleDocsService(str(creds_file))

        assert service.credentials_path == str(creds_file)
        assert service.docs_service is not None

    def test_init_without_path_raises(self):
        """Test that missing credentials raises GoogleDocsError."""
        with pytest.raises(GoogleDocsError, match="credentials_path is required"):
            GoogleDocsService()

    @patch("src.drive_sync.gdocs.service_account.Credentials.from_service_account_file")
    def test_init_with_missing_file_raises(self, mock_from_file):
        """Test that non-existent credentials file raises GoogleDocsError."""
        with pytest.raises(GoogleDocsError, match="Credentials not found"):
            GoogleDocsService("/nonexistent/credentials.json")


class TestFindDiagramMarkers:
    """Test diagram marker detection in documents."""

    def _make_service(self, doc_content):
        """Helper: create service with mocked docs API returning given content."""
        mock_auth = _make_mock_auth()
        mock_auth.docs_service.documents().get().execute.return_value = {
            "body": {"content": doc_content}
        }
        service = GoogleDocsService(mock_auth)
        return service

    def test_finds_single_marker(self):
        """Test finding a single diagram marker."""
        content = [{
            "paragraph": {
                "elements": [{
                    "textRun": {
                        "content": "Before [DIAGRAM:flowchart] After",
                    },
                    "startIndex": 10,
                }]
            }
        }]
        service = self._make_service(content)
        markers = service.find_diagram_markers("doc-id")

        assert len(markers) == 1
        assert markers[0]["name"] == "flowchart"
        assert markers[0]["length"] == len("[DIAGRAM:flowchart]")

    def test_finds_multiple_markers(self):
        """Test finding multiple diagram markers."""
        content = [
            {
                "paragraph": {
                    "elements": [{
                        "textRun": {"content": "[DIAGRAM:flow1]"},
                        "startIndex": 0,
                    }]
                }
            },
            {
                "paragraph": {
                    "elements": [{
                        "textRun": {"content": "[DIAGRAM:flow2]"},
                        "startIndex": 50,
                    }]
                }
            },
        ]
        service = self._make_service(content)
        markers = service.find_diagram_markers("doc-id")

        assert len(markers) == 2
        assert markers[0]["name"] == "flow1"
        assert markers[1]["name"] == "flow2"

    def test_no_markers_returns_empty(self):
        """Test that document without markers returns empty list."""
        content = [{
            "paragraph": {
                "elements": [{
                    "textRun": {"content": "Just regular text"},
                    "startIndex": 0,
                }]
            }
        }]
        service = self._make_service(content)
        markers = service.find_diagram_markers("doc-id")

        assert markers == []

    def test_http_error_returns_empty(self):
        """Test that HttpError returns empty list."""
        from googleapiclient.errors import HttpError

        mock_auth = _make_mock_auth()
        mock_auth.docs_service.documents().get().execute.side_effect = HttpError(
            resp=MagicMock(status=404), content=b"Not found"
        )
        service = GoogleDocsService(mock_auth)

        markers = service.find_diagram_markers("bad-doc-id")
        assert markers == []


class TestEmbedDiagram:
    """Test diagram embedding in documents."""

    def _make_service(self):
        """Helper: create service with mocked docs API."""
        mock_auth = _make_mock_auth()
        service = GoogleDocsService(mock_auth)
        return service

    def test_embed_calls_batch_update(self):
        """Test that embed_diagram calls batchUpdate with correct requests."""
        service = self._make_service()

        service.embed_diagram(
            doc_id="doc-123",
            diagram_name="flowchart",
            image_url="https://drive.google.com/uc?id=img-123",
            marker_index=10,
            marker_length=19,
            width_pt=500,
            height_pt=350,
        )

        service.docs_service.documents().batchUpdate.assert_called_once()
        call_kwargs = service.docs_service.documents().batchUpdate.call_args
        assert call_kwargs[1]["documentId"] == "doc-123"

    def test_embed_http_error_raises(self):
        """Test that HttpError during embed raises GoogleDocsError."""
        from googleapiclient.errors import HttpError

        service = self._make_service()
        service.docs_service.documents().batchUpdate().execute.side_effect = HttpError(
            resp=MagicMock(status=500), content=b"Server error"
        )

        with pytest.raises(GoogleDocsError, match="Failed to embed diagram"):
            service.embed_diagram(
                doc_id="doc-123",
                diagram_name="test",
                image_url="https://example.com/img.png",
                marker_index=0,
                marker_length=10,
            )


class TestParseHeadings:
    """Test heading parsing from document structure."""

    def test_parses_heading_with_id(self):
        """Test parsing a simple heading with headingId."""
        document = {
            "body": {
                "content": [{
                    "paragraph": {
                        "paragraphStyle": {
                            "namedStyleType": "HEADING_1",
                            "headingId": "h.abc123",
                        },
                        "elements": [{
                            "textRun": {"content": "Introduction\n"},
                            "startIndex": 0,
                        }],
                    }
                }]
            }
        }
        result = GoogleDocsService._parse_headings(document)

        assert "introduction" in result
        assert result["introduction"]["text"] == "Introduction"
        assert result["introduction"]["level"] == 1
        assert result["introduction"]["heading_id"] == "h.abc123"

    def test_parses_multiple_heading_levels(self):
        """Test parsing H1, H2, H3 headings."""
        document = {
            "body": {
                "content": [
                    {
                        "paragraph": {
                            "paragraphStyle": {
                                "namedStyleType": "HEADING_1",
                                "headingId": "h.1",
                            },
                            "elements": [{"textRun": {"content": "Title\n"}, "startIndex": 0}],
                        }
                    },
                    {
                        "paragraph": {
                            "paragraphStyle": {
                                "namedStyleType": "HEADING_2",
                                "headingId": "h.2",
                            },
                            "elements": [{"textRun": {"content": "Section\n"}, "startIndex": 10}],
                        }
                    },
                    {
                        "paragraph": {
                            "paragraphStyle": {
                                "namedStyleType": "HEADING_3",
                                "headingId": "h.3",
                            },
                            "elements": [{"textRun": {"content": "Subsection\n"}, "startIndex": 20}],
                        }
                    },
                ]
            }
        }
        result = GoogleDocsService._parse_headings(document)

        assert len(result) == 3
        assert result["title"]["level"] == 1
        assert result["section"]["level"] == 2
        assert result["subsection"]["level"] == 3

    def test_handles_duplicate_heading_text(self):
        """Test unique slug generation for duplicate headings."""
        document = {
            "body": {
                "content": [
                    {
                        "paragraph": {
                            "paragraphStyle": {
                                "namedStyleType": "HEADING_2",
                                "headingId": "h.1",
                            },
                            "elements": [{"textRun": {"content": "Overview\n"}, "startIndex": 0}],
                        }
                    },
                    {
                        "paragraph": {
                            "paragraphStyle": {
                                "namedStyleType": "HEADING_2",
                                "headingId": "h.2",
                            },
                            "elements": [{"textRun": {"content": "Overview\n"}, "startIndex": 20}],
                        }
                    },
                ]
            }
        }
        result = GoogleDocsService._parse_headings(document)

        assert "overview" in result
        assert "overview-1" in result

    def test_skips_heading_without_id(self):
        """Test that headings without headingId are skipped."""
        document = {
            "body": {
                "content": [{
                    "paragraph": {
                        "paragraphStyle": {
                            "namedStyleType": "HEADING_1",
                        },
                        "elements": [{"textRun": {"content": "No ID\n"}, "startIndex": 0}],
                    }
                }]
            }
        }
        result = GoogleDocsService._parse_headings(document)
        assert len(result) == 0

    def test_skips_non_heading_paragraphs(self):
        """Test that normal paragraphs are skipped."""
        document = {
            "body": {
                "content": [{
                    "paragraph": {
                        "paragraphStyle": {
                            "namedStyleType": "NORMAL_TEXT",
                        },
                        "elements": [{"textRun": {"content": "Regular text\n"}, "startIndex": 0}],
                    }
                }]
            }
        }
        result = GoogleDocsService._parse_headings(document)
        assert len(result) == 0

    def test_empty_document(self):
        """Test parsing empty document."""
        document = {"body": {"content": []}}
        result = GoogleDocsService._parse_headings(document)
        assert result == {}


class TestFindAnchorLinks:
    """Test anchor link discovery in documents."""

    def test_finds_anchor_link(self):
        """Test finding a hash-prefixed anchor link."""
        document = {
            "body": {
                "content": [{
                    "paragraph": {
                        "elements": [{
                            "textRun": {
                                "content": "Jump to section",
                                "textStyle": {
                                    "link": {"url": "#introduction"}
                                },
                            },
                            "startIndex": 0,
                            "endIndex": 15,
                        }]
                    }
                }]
            }
        }
        result = GoogleDocsService._find_anchor_links(document)

        assert len(result) == 1
        assert result[0]["anchor"] == "introduction"
        assert result[0]["text"] == "Jump to section"

    def test_ignores_external_links(self):
        """Test that external URLs (with ://) are ignored."""
        document = {
            "body": {
                "content": [{
                    "paragraph": {
                        "elements": [{
                            "textRun": {
                                "content": "Google",
                                "textStyle": {
                                    "link": {"url": "https://google.com"}
                                },
                            },
                            "startIndex": 0,
                            "endIndex": 6,
                        }]
                    }
                }]
            }
        }
        result = GoogleDocsService._find_anchor_links(document)
        assert len(result) == 0

    def test_ignores_elements_without_links(self):
        """Test that elements without links are ignored."""
        document = {
            "body": {
                "content": [{
                    "paragraph": {
                        "elements": [{
                            "textRun": {
                                "content": "Plain text",
                                "textStyle": {},
                            },
                            "startIndex": 0,
                            "endIndex": 10,
                        }]
                    }
                }]
            }
        }
        result = GoogleDocsService._find_anchor_links(document)
        assert len(result) == 0

    def test_empty_document(self):
        """Test finding anchor links in empty document."""
        document = {"body": {"content": []}}
        result = GoogleDocsService._find_anchor_links(document)
        assert result == []


class TestConvertAnchorLinks:
    """Test anchor link conversion to headingId links."""

    def _make_service(self):
        """Helper: create service with mocked docs API."""
        mock_auth = _make_mock_auth()
        service = GoogleDocsService(mock_auth)
        return service

    def test_converts_matching_anchor(self):
        """Test converting anchor link that matches a heading."""
        service = self._make_service()

        heading_map = {
            "introduction": {
                "text": "Introduction",
                "level": 1,
                "heading_id": "h.abc123",
                "index": 0,
            }
        }
        anchor_links = [{
            "anchor": "introduction",
            "start_index": 50,
            "end_index": 70,
            "text": "Go to Introduction",
        }]

        count = service.convert_anchor_links("doc-123", heading_map, anchor_links)

        assert count == 1
        service.docs_service.documents().batchUpdate.assert_called_once()

    def test_returns_zero_for_no_links(self):
        """Test that empty anchor_links returns 0."""
        service = self._make_service()
        count = service.convert_anchor_links("doc-123", {}, [])
        assert count == 0

    def test_skips_unmatched_anchors(self):
        """Test that anchors not in heading_map are skipped."""
        service = self._make_service()

        heading_map = {
            "section-a": {
                "text": "Section A",
                "level": 2,
                "heading_id": "h.xyz",
                "index": 0,
            }
        }
        anchor_links = [{
            "anchor": "nonexistent-heading",
            "start_index": 50,
            "end_index": 70,
            "text": "Bad link",
        }]

        count = service.convert_anchor_links("doc-123", heading_map, anchor_links)
        assert count == 0

    def test_http_error_raises_google_docs_error(self):
        """Test that HttpError during batchUpdate raises GoogleDocsError."""
        from googleapiclient.errors import HttpError

        service = self._make_service()
        service.docs_service.documents().batchUpdate().execute.side_effect = HttpError(
            resp=MagicMock(status=500), content=b"Server error"
        )

        heading_map = {
            "intro": {"text": "Intro", "level": 1, "heading_id": "h.1", "index": 0}
        }
        anchor_links = [{"anchor": "intro", "start_index": 10, "end_index": 20, "text": "Intro"}]

        with pytest.raises(GoogleDocsError, match="Failed to convert anchor links"):
            service.convert_anchor_links("doc-123", heading_map, anchor_links)


class TestProcessAnchorLinks:
    """Test the complete anchor link processing workflow."""

    def _make_service_with_doc(self, document):
        """Helper: create service returning given document on get()."""
        mock_auth = _make_mock_auth()
        mock_auth.docs_service.documents().get().execute.return_value = document
        service = GoogleDocsService(mock_auth)
        return service

    def test_returns_zero_no_headings(self):
        """Test that no headings results in 0 conversions."""
        document = {"body": {"content": []}}
        service = self._make_service_with_doc(document)

        count = service.process_anchor_links("doc-123")
        assert count == 0

    def test_returns_zero_no_anchor_links(self):
        """Test that headings but no anchor links returns 0."""
        document = {
            "body": {
                "content": [{
                    "paragraph": {
                        "paragraphStyle": {
                            "namedStyleType": "HEADING_1",
                            "headingId": "h.1",
                        },
                        "elements": [{"textRun": {"content": "Title\n"}, "startIndex": 0}],
                    }
                }]
            }
        }
        service = self._make_service_with_doc(document)

        count = service.process_anchor_links("doc-123")
        assert count == 0


class TestGoogleDocsError:
    """Test GoogleDocsError exception."""

    def test_is_exception(self):
        """Test that GoogleDocsError is an Exception subclass."""
        assert issubclass(GoogleDocsError, Exception)

    def test_carries_message(self):
        """Test that error carries a descriptive message."""
        with pytest.raises(GoogleDocsError, match="test error"):
            raise GoogleDocsError("test error")
