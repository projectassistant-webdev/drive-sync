"""
Tests for ASCII art rendering module.

Tests render_ascii_to_image produces valid PNG bytes, handles
various ASCII art inputs, and raises ASCIIRenderError on failure.
"""

from unittest.mock import patch

import pytest

from src.drive_sync.ascii_renderer import (
    PILLOW_AVAILABLE,
    ASCIIRenderError,
    get_monospace_font,
    render_ascii_to_image,
)


@pytest.mark.skipif(not PILLOW_AVAILABLE, reason="Pillow not installed")
class TestRenderAsciiToImage:
    """Test ASCII to PNG rendering."""

    def test_simple_text_produces_bytes(self):
        """Test that simple text produces non-empty PNG bytes."""
        result = render_ascii_to_image("Hello World")
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_output_is_valid_png(self):
        """Test that output starts with PNG magic bytes."""
        result = render_ascii_to_image("Test")
        assert result[:4] == b"\x89PNG"

    def test_multiline_text(self):
        """Test rendering multiline ASCII art."""
        ascii_art = (
            "+--------+\n"
            "| Header |\n"
            "+--------+\n"
            "| Cell 1 |\n"
            "+--------+"
        )
        result = render_ascii_to_image(ascii_art)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_empty_string(self):
        """Test rendering empty string still produces image."""
        result = render_ascii_to_image("")
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_single_character(self):
        """Test rendering a single character."""
        result = render_ascii_to_image("X")
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_unicode_characters(self):
        """Test rendering unicode box-drawing characters."""
        box = "┌───┐\n│ A │\n└───┘"
        result = render_ascii_to_image(box)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_custom_font_size(self):
        """Test rendering with custom font size."""
        result = render_ascii_to_image("Test", font_size=20)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_custom_colors(self):
        """Test rendering with custom colors."""
        result = render_ascii_to_image(
            "Test",
            background_color="#000000",
            text_color="#FFFFFF",
            border_color="#FF0000",
        )
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_large_text(self):
        """Test rendering large text block."""
        large_text = "\n".join(["X" * 80] * 50)
        result = render_ascii_to_image(large_text)
        assert isinstance(result, bytes)
        assert len(result) > 0


class TestRenderAsciiPillowUnavailable:
    """Test behavior when Pillow is not available."""

    @patch("src.drive_sync.ascii_renderer.PILLOW_AVAILABLE", False)
    def test_raises_error_without_pillow(self):
        """Test that ASCIIRenderError is raised when Pillow unavailable."""
        with pytest.raises(ASCIIRenderError, match="Pillow is not installed"):
            render_ascii_to_image("Test")


@pytest.mark.skipif(not PILLOW_AVAILABLE, reason="Pillow not installed")
class TestGetMonospaceFont:
    """Test monospace font discovery."""

    def test_returns_font_object(self):
        """Test that get_monospace_font returns a font object."""
        font = get_monospace_font(14)
        assert font is not None

    def test_custom_size(self):
        """Test font with custom size."""
        font = get_monospace_font(20)
        assert font is not None

    @patch("os.path.exists", return_value=False)
    def test_fallback_to_default_font(self, mock_exists):
        """Test fallback to default font when no monospace font found."""
        font = get_monospace_font(14)
        assert font is not None


class TestASCIIRenderError:
    """Test ASCIIRenderError exception."""

    def test_is_exception(self):
        """Test that ASCIIRenderError is an Exception subclass."""
        assert issubclass(ASCIIRenderError, Exception)

    def test_can_be_raised_with_message(self):
        """Test that error can carry a message."""
        with pytest.raises(ASCIIRenderError, match="test error"):
            raise ASCIIRenderError("test error")
