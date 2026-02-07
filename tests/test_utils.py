"""
Tests for utility functions.

Tests heading slugification and unique slug generation including
edge cases with empty strings, special characters, and Unicode.
"""

from src.drive_sync.utils import get_unique_slug, slugify_heading


class TestSlugifyHeadingBasics:
    """Test basic slug generation from heading text."""

    def test_simple_heading(self):
        """Test basic lowercase and space-to-hyphen conversion."""
        assert slugify_heading("Hello World") == "hello-world"

    def test_preserves_numbers(self):
        """Test that numbers are preserved in slugs."""
        assert slugify_heading("Section 42") == "section-42"

    def test_removes_special_chars(self):
        """Test that non-alphanumeric non-hyphen characters are removed."""
        assert slugify_heading("Hello! World?") == "hello-world"

    def test_ampersand_creates_double_hyphen(self):
        """Test that & surrounded by spaces creates double hyphen (VS Code behavior)."""
        assert slugify_heading("A & B") == "a--b"

    def test_strips_leading_trailing_hyphens(self):
        """Test that leading and trailing hyphens are stripped."""
        assert slugify_heading("- Hello -") == "hello"

    def test_preserves_multiple_hyphens(self):
        """Test that consecutive hyphens are NOT collapsed (VS Code behavior)."""
        assert slugify_heading("A & B & C") == "a--b--c"


class TestSlugifyHeadingEdgeCases:
    """Test edge cases for slug generation."""

    def test_empty_string(self):
        """Test that empty string returns empty slug."""
        assert slugify_heading("") == ""

    def test_whitespace_only(self):
        """Test that whitespace-only string returns empty slug."""
        assert slugify_heading("   ") == ""
        assert slugify_heading("\t\n") == ""

    def test_only_special_chars(self):
        """Test heading with only special characters."""
        result = slugify_heading("@#$%^")
        assert result == ""

    def test_only_hyphens(self):
        """Test heading that is only hyphens after processing."""
        assert slugify_heading("---") == ""

    def test_single_character(self):
        """Test single character heading."""
        assert slugify_heading("A") == "a"

    def test_very_long_heading(self):
        """Test that very long headings are handled without error."""
        long_heading = "Word " * 100
        slug = slugify_heading(long_heading.strip())
        assert isinstance(slug, str)
        assert len(slug) > 0


class TestSlugifyHeadingUnicode:
    """Test Unicode handling in slug generation."""

    def test_diacritics_normalized(self):
        """Test that diacritics are normalized to ASCII equivalents."""
        assert slugify_heading("Café") == "cafe"
        assert slugify_heading("Über") == "uber"
        assert slugify_heading("Résumé") == "resume"

    def test_emoji_removed(self):
        """Test that emoji characters are removed."""
        assert slugify_heading("Quick Start") == "quick-start"

    def test_cjk_characters_removed(self):
        """Test that CJK characters are removed (not ASCII-translatable)."""
        # Use actual CJK characters (U+4F60=ni, U+597D=hao)
        assert slugify_heading("Hello \u4f60\u597d") == "hello"


class TestGetUniqueSlug:
    """Test unique slug generation with duplicate tracking."""

    def test_first_occurrence_no_suffix(self):
        """Test that first occurrence has no suffix."""
        seen = {}
        assert get_unique_slug("test", seen) == "test"

    def test_second_occurrence_suffix_1(self):
        """Test that second occurrence gets -1 suffix."""
        seen = {}
        get_unique_slug("test", seen)
        assert get_unique_slug("test", seen) == "test-1"

    def test_third_occurrence_suffix_2(self):
        """Test that third occurrence gets -2 suffix."""
        seen = {}
        get_unique_slug("test", seen)
        get_unique_slug("test", seen)
        assert get_unique_slug("test", seen) == "test-2"

    def test_different_slugs_independent(self):
        """Test that different base slugs are tracked independently."""
        seen = {}
        assert get_unique_slug("alpha", seen) == "alpha"
        assert get_unique_slug("beta", seen) == "beta"
        assert get_unique_slug("alpha", seen) == "alpha-1"
        assert get_unique_slug("beta", seen) == "beta-1"

    def test_seen_dict_mutated(self):
        """Test that the seen dict is properly mutated in-place."""
        seen = {}
        get_unique_slug("test", seen)
        assert "test" in seen
        assert seen["test"] == 0

        get_unique_slug("test", seen)
        assert seen["test"] == 1

    def test_empty_slug(self):
        """Test unique slug with empty base slug."""
        seen = {}
        assert get_unique_slug("", seen) == ""
        assert get_unique_slug("", seen) == "-1"
