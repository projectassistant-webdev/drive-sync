"""
Tests for anchor link conversion functionality.

Tests the complete workflow:
1. Slugify heading text to markdown-compatible anchors
2. Discover headings in Google Docs with headingId
3. Detect and convert anchor links in documents
"""

import pytest
from src.drive_sync.utils import slugify_heading, get_unique_slug


class TestSlugifyHeading:
    """Test markdown-compatible anchor slug generation."""

    def test_basic_transformations(self):
        """Test basic heading transformations matching VS Code/CommonMark."""
        # Double hyphen from removed ampersand (& surrounded by spaces)
        assert slugify_heading("Timeline & Rollout Strategy") == "timeline--rollout-strategy"

        # Parentheses and colons removed, hyphens from spaces preserved
        assert slugify_heading("Phase 1: Alpha (Weeks 1-4)") == "phase-1-alpha-weeks-1-4"

        # Apostrophe removed
        assert slugify_heading("What's Included") == "whats-included"

        # Simple case
        assert slugify_heading("API Documentation Links") == "api-documentation-links"

    def test_emoji_handling(self):
        """Test emoji removal from slugs."""
        assert slugify_heading("🚀 Quick Start") == "quick-start"
        assert slugify_heading("Features ✨") == "features"
        assert slugify_heading("🎨 Design System 🎨") == "design-system"

    def test_diacritic_normalization(self):
        """Test diacritics/accents normalized to ASCII equivalents."""
        assert slugify_heading("Café Setup") == "cafe-setup"
        assert slugify_heading("Über Configuration") == "uber-configuration"
        assert slugify_heading("Résumé Builder") == "resume-builder"
        assert slugify_heading("Piñata Party") == "pinata-party"
        assert slugify_heading("Naïve Approach") == "naive-approach"

    def test_edge_cases(self):
        """Test edge cases for slug generation."""
        # Empty/whitespace
        assert slugify_heading("") == ""
        assert slugify_heading("   ") == ""
        assert slugify_heading("\t\n  \t") == ""

        # Numbers
        assert slugify_heading("123 Numbers") == "123-numbers"
        assert slugify_heading("2024 Goals") == "2024-goals"

        # Special characters
        assert slugify_heading("Hello @ World!") == "hello--world"
        assert slugify_heading("100% Complete") == "100-complete"
        assert slugify_heading("Price: $99.99") == "price-9999"

        # Leading/trailing hyphens stripped
        assert slugify_heading("- Leading Hyphen") == "leading-hyphen"
        assert slugify_heading("Trailing Hyphen -") == "trailing-hyphen"
        assert slugify_heading("-- Both --") == "both"

    def test_multiple_hyphens_preserved(self):
        """Test that multiple consecutive hyphens are preserved (VS Code behavior)."""
        # Ampersand removal leaves double hyphen
        assert slugify_heading("A & B & C") == "a--b--c"

        # Multiple spaces become multiple hyphens (but ampersand removal is primary source)
        assert slugify_heading("Timeline  &  Strategy") == "timeline----strategy"

    def test_unicode_edge_cases(self):
        """Test various unicode characters."""
        # CJK characters removed (not ASCII)
        assert slugify_heading("Hello 世界") == "hello"

        # Mixed unicode and ASCII (emoji removal leaves double hyphen)
        assert slugify_heading("Café ☕ Menu") == "cafe--menu"


class TestDuplicateHeadingHandling:
    """Test duplicate heading slug handling."""

    def test_unique_slug_generation(self):
        """Test that duplicate headings get -1, -2, etc suffixes."""
        seen = {}

        # First occurrence - no suffix
        assert get_unique_slug("overview", seen) == "overview"

        # Second occurrence - suffix -1
        assert get_unique_slug("overview", seen) == "overview-1"

        # Third occurrence - suffix -2
        assert get_unique_slug("overview", seen) == "overview-2"

        # Different heading - no suffix
        assert get_unique_slug("introduction", seen) == "introduction"

        # Another duplicate of overview - suffix -3
        assert get_unique_slug("overview", seen) == "overview-3"

    def test_empty_seen_dict(self):
        """Test with empty tracking dict."""
        seen = {}
        assert get_unique_slug("test", seen) == "test"

    def test_reusing_seen_dict(self):
        """Test that seen dict is properly mutated."""
        seen = {}
        slug1 = get_unique_slug("test", seen)
        slug2 = get_unique_slug("test", seen)

        assert slug1 != slug2
        assert slug1 == "test"
        assert slug2 == "test-1"
        assert "test" in seen
        assert seen["test"] == 1  # Counter incremented


class TestHeadingDiscovery:
    """Test heading discovery from Google Docs structure."""

    def test_get_heading_bookmarks_basic(self):
        """Test basic heading extraction with headingId."""
        from src.drive_sync.gdocs import GoogleDocsService

        # Mock Google Docs document structure
        mock_doc = {
            'body': {
                'content': [
                    {
                        'paragraph': {
                            'paragraphStyle': {
                                'namedStyleType': 'HEADING_1',
                                'headingId': 'h.abc123'
                            },
                            'elements': [
                                {
                                    'textRun': {
                                        'content': 'Introduction\n'
                                    },
                                    'startIndex': 1
                                }
                            ]
                        }
                    },
                    {
                        'paragraph': {
                            'paragraphStyle': {
                                'namedStyleType': 'HEADING_2',
                                'headingId': 'h.def456'
                            },
                            'elements': [
                                {
                                    'textRun': {
                                        'content': 'Timeline & Rollout Strategy\n'
                                    },
                                    'startIndex': 50
                                }
                            ]
                        }
                    }
                ]
            }
        }

        # This should extract headings and generate slug map
        heading_map = GoogleDocsService._parse_headings(mock_doc)

        assert 'introduction' in heading_map
        assert heading_map['introduction']['heading_id'] == 'h.abc123'
        assert heading_map['introduction']['text'] == 'Introduction'
        assert heading_map['introduction']['level'] == 1

        assert 'timeline--rollout-strategy' in heading_map
        assert heading_map['timeline--rollout-strategy']['heading_id'] == 'h.def456'
        assert heading_map['timeline--rollout-strategy']['text'] == 'Timeline & Rollout Strategy'
        assert heading_map['timeline--rollout-strategy']['level'] == 2

    def test_duplicate_heading_handling(self):
        """Test that duplicate headings get unique slugs."""
        from src.drive_sync.gdocs import GoogleDocsService

        mock_doc = {
            'body': {
                'content': [
                    {
                        'paragraph': {
                            'paragraphStyle': {
                                'namedStyleType': 'HEADING_2',
                                'headingId': 'h.first'
                            },
                            'elements': [
                                {'textRun': {'content': 'Overview\n'}, 'startIndex': 1}
                            ]
                        }
                    },
                    {
                        'paragraph': {
                            'paragraphStyle': {
                                'namedStyleType': 'HEADING_2',
                                'headingId': 'h.second'
                            },
                            'elements': [
                                {'textRun': {'content': 'Overview\n'}, 'startIndex': 50}
                            ]
                        }
                    },
                    {
                        'paragraph': {
                            'paragraphStyle': {
                                'namedStyleType': 'HEADING_2',
                                'headingId': 'h.third'
                            },
                            'elements': [
                                {'textRun': {'content': 'Overview\n'}, 'startIndex': 100}
                            ]
                        }
                    }
                ]
            }
        }

        heading_map = GoogleDocsService._parse_headings(mock_doc)

        # First occurrence - no suffix
        assert 'overview' in heading_map
        assert heading_map['overview']['heading_id'] == 'h.first'

        # Second occurrence - suffix -1
        assert 'overview-1' in heading_map
        assert heading_map['overview-1']['heading_id'] == 'h.second'

        # Third occurrence - suffix -2
        assert 'overview-2' in heading_map
        assert heading_map['overview-2']['heading_id'] == 'h.third'

    def test_empty_document(self):
        """Test handling of document with no headings."""
        from src.drive_sync.gdocs import GoogleDocsService

        mock_doc = {
            'body': {
                'content': [
                    {
                        'paragraph': {
                            'paragraphStyle': {
                                'namedStyleType': 'NORMAL_TEXT'
                            },
                            'elements': [
                                {'textRun': {'content': 'Just text\n'}}
                            ]
                        }
                    }
                ]
            }
        }

        heading_map = GoogleDocsService._parse_headings(mock_doc)
        assert heading_map == {}


class TestAnchorLinkConversion:
    """Test anchor link detection and conversion."""

    def test_detect_anchor_links(self):
        """Test detection of internal anchor links in document."""
        from src.drive_sync.gdocs import GoogleDocsService

        mock_doc = {
            'body': {
                'content': [
                    {
                        'paragraph': {
                            'elements': [
                                {
                                    'textRun': {
                                        'content': 'See ',
                                        'textStyle': {}
                                    },
                                    'startIndex': 10
                                },
                                {
                                    'textRun': {
                                        'content': 'Timeline & Rollout Strategy',
                                        'textStyle': {
                                            'link': {'url': '#timeline--rollout-strategy'}
                                        }
                                    },
                                    'startIndex': 14,
                                    'endIndex': 41
                                },
                                {
                                    'textRun': {
                                        'content': ' for details.\n'
                                    },
                                    'startIndex': 41
                                }
                            ]
                        }
                    }
                ]
            }
        }

        anchor_links = GoogleDocsService._find_anchor_links(mock_doc)

        assert len(anchor_links) == 1
        assert anchor_links[0]['anchor'] == 'timeline--rollout-strategy'
        assert anchor_links[0]['start_index'] == 14
        assert anchor_links[0]['end_index'] == 41
        assert anchor_links[0]['text'] == 'Timeline & Rollout Strategy'

    def test_ignore_external_links(self):
        """Test that external URLs are not detected as anchor links."""
        from src.drive_sync.gdocs import GoogleDocsService

        mock_doc = {
            'body': {
                'content': [
                    {
                        'paragraph': {
                            'elements': [
                                {
                                    'textRun': {
                                        'content': 'Visit ',
                                        'textStyle': {}
                                    }
                                },
                                {
                                    'textRun': {
                                        'content': 'example.com',
                                        'textStyle': {
                                            'link': {'url': 'https://example.com/page#section'}
                                        }
                                    },
                                    'startIndex': 10,
                                    'endIndex': 21
                                }
                            ]
                        }
                    }
                ]
            }
        }

        anchor_links = GoogleDocsService._find_anchor_links(mock_doc)
        assert len(anchor_links) == 0  # External link should be ignored

    def test_convert_anchor_links(self):
        """Test conversion of anchor links to headingId links."""
        from src.drive_sync.gdocs import GoogleDocsService
        from unittest.mock import Mock, MagicMock

        # Mock Google Docs service
        mock_docs_service = Mock()
        mock_batch_update = MagicMock()
        mock_docs_service.documents().batchUpdate.return_value = mock_batch_update
        mock_batch_update.execute.return_value = {}

        # Create GoogleDocsService instance with mock
        gdocs = GoogleDocsService.__new__(GoogleDocsService)
        gdocs.docs_service = mock_docs_service

        # Mock heading map
        heading_map = {
            'timeline--rollout-strategy': {
                'heading_id': 'h.abc123',
                'text': 'Timeline & Rollout Strategy'
            }
        }

        # Mock anchor links
        anchor_links = [
            {
                'anchor': 'timeline--rollout-strategy',
                'start_index': 14,
                'end_index': 41,
                'text': 'Timeline & Rollout Strategy'
            }
        ]

        # Call conversion method
        doc_id = 'test-doc-id'
        result = gdocs.convert_anchor_links(doc_id, heading_map, anchor_links)

        # Verify batchUpdate was called with correct request
        mock_batch_update.execute.assert_called_once()
        call_args = mock_docs_service.documents().batchUpdate.call_args

        # Check that correct documentId was passed
        assert call_args[1]['documentId'] == doc_id

        # Check request structure
        requests = call_args[1]['body']['requests']
        assert len(requests) == 1

        update_request = requests[0]['updateTextStyle']
        assert update_request['range']['startIndex'] == 14
        assert update_request['range']['endIndex'] == 41
        assert update_request['textStyle']['link']['headingId'] == 'h.abc123'
        assert update_request['fields'] == 'link'

        assert result == 1  # 1 link converted

    def test_convert_multiple_links_reverse_order(self):
        """Test that multiple links are processed in reverse index order."""
        from src.drive_sync.gdocs import GoogleDocsService
        from unittest.mock import Mock, MagicMock

        mock_docs_service = Mock()
        mock_batch_update = MagicMock()
        mock_docs_service.documents().batchUpdate.return_value = mock_batch_update
        mock_batch_update.execute.return_value = {}

        gdocs = GoogleDocsService.__new__(GoogleDocsService)
        gdocs.docs_service = mock_docs_service

        heading_map = {
            'introduction': {'heading_id': 'h.111'},
            'conclusion': {'heading_id': 'h.222'}
        }

        # Links in forward order
        anchor_links = [
            {'anchor': 'introduction', 'start_index': 10, 'end_index': 22},
            {'anchor': 'conclusion', 'start_index': 50, 'end_index': 60}
        ]

        gdocs.convert_anchor_links('doc-id', heading_map, anchor_links)

        # Check that requests are in reverse order (highest index first)
        requests = mock_docs_service.documents().batchUpdate.call_args[1]['body']['requests']
        assert len(requests) == 2

        # First request should be for higher index (conclusion)
        assert requests[0]['updateTextStyle']['range']['startIndex'] == 50
        assert requests[0]['updateTextStyle']['textStyle']['link']['headingId'] == 'h.222'

        # Second request should be for lower index (introduction)
        assert requests[1]['updateTextStyle']['range']['startIndex'] == 10
        assert requests[1]['updateTextStyle']['textStyle']['link']['headingId'] == 'h.111'

    def test_missing_heading_warning(self, caplog):
        """Test that missing headings are warned but don't fail conversion."""
        from src.drive_sync.gdocs import GoogleDocsService
        from unittest.mock import Mock, MagicMock
        import logging

        mock_docs_service = Mock()
        mock_batch_update = MagicMock()
        mock_docs_service.documents().batchUpdate.return_value = mock_batch_update
        mock_batch_update.execute.return_value = {}

        gdocs = GoogleDocsService.__new__(GoogleDocsService)
        gdocs.docs_service = mock_docs_service

        heading_map = {
            'exists': {'heading_id': 'h.123'}
        }

        # One valid link, one missing
        anchor_links = [
            {'anchor': 'exists', 'start_index': 10, 'end_index': 16},
            {'anchor': 'does-not-exist', 'start_index': 50, 'end_index': 65}
        ]

        # Capture log output
        with caplog.at_level(logging.WARNING):
            result = gdocs.convert_anchor_links('doc-id', heading_map, anchor_links)

        # Should warn about missing heading
        assert any('does-not-exist' in record.message for record in caplog.records)

        # Should still convert the valid link
        assert result == 1

        requests = mock_docs_service.documents().batchUpdate.call_args[1]['body']['requests']
        assert len(requests) == 1
        assert requests[0]['updateTextStyle']['textStyle']['link']['headingId'] == 'h.123'


class TestIntegration:
    """Test complete end-to-end workflow."""

    def test_process_anchor_links_complete_workflow(self):
        """Test complete workflow: get doc, parse headings, find links, convert."""
        from src.drive_sync.gdocs import GoogleDocsService
        from unittest.mock import Mock, MagicMock

        # Mock Google Docs service
        mock_docs_service = Mock()

        # Mock documents().get() - returns document with headings and anchor links
        mock_get = MagicMock()
        mock_docs_service.documents().get.return_value = mock_get
        mock_get.execute.return_value = {
            'body': {
                'content': [
                    # Heading
                    {
                        'paragraph': {
                            'paragraphStyle': {
                                'namedStyleType': 'HEADING_2',
                                'headingId': 'h.abc123'
                            },
                            'elements': [
                                {'textRun': {'content': 'Timeline & Rollout Strategy\n'}, 'startIndex': 1}
                            ]
                        }
                    },
                    # Link to heading
                    {
                        'paragraph': {
                            'elements': [
                                {
                                    'textRun': {
                                        'content': 'See ',
                                        'textStyle': {}
                                    }
                                },
                                {
                                    'textRun': {
                                        'content': 'Timeline & Rollout Strategy',
                                        'textStyle': {
                                            'link': {'url': '#timeline--rollout-strategy'}
                                        }
                                    },
                                    'startIndex': 100,
                                    'endIndex': 127
                                }
                            ]
                        }
                    }
                ]
            }
        }

        # Mock documents().batchUpdate()
        mock_batch_update = MagicMock()
        mock_docs_service.documents().batchUpdate.return_value = mock_batch_update
        mock_batch_update.execute.return_value = {}

        # Create GoogleDocsService instance
        gdocs = GoogleDocsService.__new__(GoogleDocsService)
        gdocs.docs_service = mock_docs_service

        # Call complete workflow
        result = gdocs.process_anchor_links('test-doc-id')

        # Verify workflow executed correctly
        assert result == 1  # 1 link converted

        # Verify documents().get was called
        mock_docs_service.documents().get.assert_called_once_with(documentId='test-doc-id')

        # Verify batchUpdate was called with correct request
        mock_batch_update.execute.assert_called_once()
        requests = mock_docs_service.documents().batchUpdate.call_args[1]['body']['requests']
        assert len(requests) == 1
        assert requests[0]['updateTextStyle']['textStyle']['link']['headingId'] == 'h.abc123'
