"""
Tests for code block rendering module.

Tests render_code_to_image produces valid PNG bytes, handles
different language highlighting, and raises CodeRenderError on failure.
"""

from unittest.mock import patch

import pytest

from src.drive_sync.code_renderer import (
    LANGUAGE_ALIASES,
    PILLOW_AVAILABLE,
    PYGMENTS_AVAILABLE,
    CodeRenderError,
    get_code_font,
    get_lexer,
    render_code_to_image,
    render_code_to_image_simple,
)


@pytest.mark.skipif(
    not PYGMENTS_AVAILABLE or not PILLOW_AVAILABLE,
    reason="Pygments or Pillow not installed",
)
class TestRenderCodeToImage:
    """Test code-to-PNG rendering with Pygments."""

    def test_python_code_produces_bytes(self):
        """Test that Python code produces non-empty PNG bytes."""
        code = "def hello():\n    print('world')"
        result = render_code_to_image(code, language="python")
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_output_is_valid_png(self):
        """Test that output starts with PNG magic bytes."""
        result = render_code_to_image("x = 1", language="python")
        assert result[:4] == b"\x89PNG"

    def test_javascript_code(self):
        """Test rendering JavaScript code."""
        code = "const x = () => console.log('hi');"
        result = render_code_to_image(code, language="javascript")
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_sql_code(self):
        """Test rendering SQL code."""
        code = "SELECT * FROM users WHERE active = true;"
        result = render_code_to_image(code, language="sql")
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_auto_detect_language(self):
        """Test rendering with auto language detection (empty language)."""
        code = "#!/bin/bash\necho 'hello'"
        result = render_code_to_image(code, language="")
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_custom_style(self):
        """Test rendering with a different Pygments style."""
        code = "x = 1"
        result = render_code_to_image(code, language="python", style="friendly")
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_without_line_numbers(self):
        """Test rendering without line numbers."""
        code = "x = 1"
        result = render_code_to_image(code, language="python", line_numbers=False)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_multiline_code(self):
        """Test rendering multiline code block."""
        code = "\n".join([f"line_{i} = {i}" for i in range(20)])
        result = render_code_to_image(code, language="python")
        assert isinstance(result, bytes)
        assert len(result) > 0


@pytest.mark.skipif(not PYGMENTS_AVAILABLE, reason="Pygments not installed")
class TestGetLexer:
    """Test Pygments lexer selection."""

    def test_known_language(self):
        """Test getting lexer for a known language."""
        lexer = get_lexer("python", "")
        assert lexer is not None
        assert "Python" in lexer.name or "python" in lexer.name.lower()

    def test_language_alias(self):
        """Test language alias resolution (js -> javascript)."""
        lexer = get_lexer("js", "")
        assert lexer is not None

    def test_unknown_language_guesses(self):
        """Test that unknown language falls back to guessing."""
        lexer = get_lexer("nonexistent_language_xyz", "print('hello')")
        assert lexer is not None

    def test_empty_language_guesses(self):
        """Test that empty language string triggers guessing."""
        lexer = get_lexer("", "def hello(): pass")
        assert lexer is not None

    def test_alias_mapping_completeness(self):
        """Test that expected aliases exist in the mapping."""
        assert "js" in LANGUAGE_ALIASES
        assert "ts" in LANGUAGE_ALIASES
        assert "py" in LANGUAGE_ALIASES
        assert "sh" in LANGUAGE_ALIASES
        assert "yml" in LANGUAGE_ALIASES


class TestGetCodeFont:
    """Test code font discovery."""

    def test_returns_string_or_none(self):
        """Test that get_code_font returns a path string or None."""
        result = get_code_font(14)
        assert result is None or isinstance(result, str)

    @patch("os.path.exists", return_value=False)
    def test_returns_none_when_no_fonts(self, mock_exists):
        """Test that None is returned when no fonts found."""
        result = get_code_font(14)
        assert result is None


class TestRenderCodeErrors:
    """Test error handling in code rendering."""

    @patch("src.drive_sync.code_renderer.PYGMENTS_AVAILABLE", False)
    def test_raises_without_pygments(self):
        """Test CodeRenderError when Pygments unavailable."""
        with pytest.raises(CodeRenderError, match="Pygments is not installed"):
            render_code_to_image("x = 1")

    @patch("src.drive_sync.code_renderer.PYGMENTS_AVAILABLE", True)
    @patch("src.drive_sync.code_renderer.PILLOW_AVAILABLE", False)
    def test_raises_without_pillow(self):
        """Test CodeRenderError when Pillow unavailable."""
        with pytest.raises(CodeRenderError, match="Pillow is not installed"):
            render_code_to_image("x = 1")


@pytest.mark.skipif(not PILLOW_AVAILABLE, reason="Pillow not installed")
class TestRenderCodeToImageSimple:
    """Test the simple (fallback) code renderer."""

    def test_produces_valid_png(self):
        """Test that simple renderer produces valid PNG."""
        result = render_code_to_image_simple("x = 1", language="python")
        assert isinstance(result, bytes)
        assert result[:4] == b"\x89PNG"

    def test_without_language_badge(self):
        """Test rendering without language badge."""
        result = render_code_to_image_simple("x = 1", show_language_badge=False)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_without_line_numbers(self):
        """Test rendering without line numbers."""
        result = render_code_to_image_simple("x = 1", show_line_numbers=False)
        assert isinstance(result, bytes)
        assert len(result) > 0

    @patch("src.drive_sync.code_renderer.PILLOW_AVAILABLE", False)
    def test_raises_without_pillow(self):
        """Test error when Pillow not available for simple renderer."""
        with pytest.raises(CodeRenderError, match="Pillow is not installed"):
            render_code_to_image_simple("x = 1")


class TestCodeRenderError:
    """Test CodeRenderError exception."""

    def test_is_exception(self):
        """Test that CodeRenderError is an Exception subclass."""
        assert issubclass(CodeRenderError, Exception)

    def test_can_carry_message(self):
        """Test that error carries a descriptive message."""
        with pytest.raises(CodeRenderError, match="rendering failed"):
            raise CodeRenderError("rendering failed")
