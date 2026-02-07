"""
Code block to PNG image renderer with syntax highlighting using Pygments.

Converts code blocks with syntax highlighting to PNG images for proper
display in Google Docs where code formatting is lost.
"""

from __future__ import annotations

import io
import logging
import os
from typing import Any

try:
    from PIL import Image, ImageDraw
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False

try:
    from pygments import highlight
    from pygments.formatters import ImageFormatter
    from pygments.lexers import TextLexer, get_lexer_by_name, guess_lexer
    from pygments.util import ClassNotFound
    PYGMENTS_AVAILABLE = True
except ImportError:
    PYGMENTS_AVAILABLE = False

logger = logging.getLogger(__name__)


class CodeRenderError(Exception):
    """Exception raised when code rendering fails"""
    pass


# Language aliases for common variations
LANGUAGE_ALIASES = {
    'js': 'javascript',
    'ts': 'typescript',
    'py': 'python',
    'rb': 'ruby',
    'sh': 'bash',
    'shell': 'bash',
    'yml': 'yaml',
    'md': 'markdown',
    'dockerfile': 'docker',
}


def get_lexer(language: str, code: str) -> Any:
    """Get the appropriate Pygments lexer for the language.

    Args:
        language: Language identifier (e.g., 'python', 'js', 'sql').
        code: The code content (used for guessing if language not specified).

    Returns:
        Pygments lexer instance.

    Raises:
        CodeRenderError: If Pygments is not installed.
    """
    if not PYGMENTS_AVAILABLE:
        raise CodeRenderError("Pygments is not installed")

    # Normalize language name
    lang = language.lower().strip() if language else ''
    lang = LANGUAGE_ALIASES.get(lang, lang)

    if lang:
        try:
            return get_lexer_by_name(lang)
        except ClassNotFound:
            logger.warning(f"Unknown language '{language}', attempting to guess")

    # Try to guess the language from code content
    try:
        return guess_lexer(code)
    except ClassNotFound:
        # Fall back to plain text
        return TextLexer()


def get_code_font(size: int = 14) -> str | None:
    """Get a monospace font path for code rendering.

    Args:
        size: Font size (not used, but kept for API consistency).

    Returns:
        Path to a monospace font file, or None to use default.
    """
    font_paths = [
        # Fira Code (preferred - has ligatures)
        "/usr/share/fonts/truetype/firacode/FiraCode-Regular.ttf",
        # DejaVu Sans Mono (installed in Docker via fonts-dejavu-core)
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        # Liberation Mono
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
        # Ubuntu Mono
        "/usr/share/fonts/truetype/ubuntu/UbuntuMono-R.ttf",
        # macOS fonts
        "/System/Library/Fonts/Menlo.ttc",
        "/Library/Fonts/SF-Mono-Regular.otf",
    ]

    for font_path in font_paths:
        if os.path.exists(font_path):
            return font_path

    return None


def render_code_to_image(
    code: str,
    language: str = '',
    style: str = 'monokai',
    font_size: int = 14,
    line_numbers: bool = True,
    line_number_bg: str = '#2d2d2d',
    line_number_fg: str = '#8f908a',
) -> bytes:
    """
    Render code with syntax highlighting as a PNG image.

    Args:
        code: The source code to render
        language: Programming language for syntax highlighting
        style: Pygments style name (default: 'monokai' - dark theme)
        font_size: Font size in points
        line_numbers: Whether to show line numbers
        line_number_bg: Background color for line numbers
        line_number_fg: Foreground color for line numbers

    Returns:
        PNG image as bytes

    Raises:
        CodeRenderError: If rendering fails
    """
    if not PYGMENTS_AVAILABLE:
        raise CodeRenderError("Pygments is not installed. Install with: pip install Pygments")

    if not PILLOW_AVAILABLE:
        raise CodeRenderError("Pillow is not installed. Install with: pip install Pillow")

    try:
        # Get the lexer for syntax highlighting
        lexer = get_lexer(language, code)

        # Get font path
        font_path = get_code_font(font_size)

        # Create the image formatter
        formatter_kwargs = {
            'style': style,
            'font_size': font_size,
            'line_numbers': line_numbers,
            'line_number_bg': line_number_bg,
            'line_number_fg': line_number_fg,
            'line_number_chars': 3,
            'line_number_pad': 6,
            'image_pad': 10,
        }

        if font_path:
            formatter_kwargs['font_name'] = font_path

        formatter = ImageFormatter(**formatter_kwargs)

        # Render the code
        image_data = highlight(code, lexer, formatter)

        logger.info(f"Rendered code block ({language or 'auto'}) to PNG ({len(image_data)} bytes)")
        return image_data

    except Exception as e:
        raise CodeRenderError(f"Failed to render code to image: {e}") from e


def render_code_to_image_simple(
    code: str,
    language: str = '',
    font_size: int = 14,
    padding: int = 16,
    background_color: str = "#1e1e1e",
    text_color: str = "#d4d4d4",
    line_number_color: str = "#858585",
    show_line_numbers: bool = True,
    show_language_badge: bool = True,
) -> bytes:
    """
    Alternative simple renderer using Pillow directly (fallback if Pygments ImageFormatter fails).

    Creates a code image with basic styling similar to VS Code dark theme.

    Args:
        code: The source code to render
        language: Programming language (for badge display)
        font_size: Font size in points
        padding: Padding around the code
        background_color: Background color (hex)
        text_color: Default text color (hex)
        line_number_color: Line number color (hex)
        show_line_numbers: Whether to show line numbers
        show_language_badge: Whether to show language badge

    Returns:
        PNG image as bytes
    """
    if not PILLOW_AVAILABLE:
        raise CodeRenderError("Pillow is not installed")

    try:
        from .ascii_renderer import get_monospace_font

        font = get_monospace_font(font_size)
        lines = code.split('\n')

        # Calculate dimensions
        bbox = font.getbbox('M')
        char_width = bbox[2] - bbox[0]
        char_height = bbox[3] - bbox[1]
        line_height = int(char_height * 1.4)

        # Line number width
        line_num_width = 0
        if show_line_numbers:
            num_digits = len(str(len(lines)))
            line_num_width = (num_digits + 2) * char_width

        # Max line width
        max_line_len = max(len(line) for line in lines) if lines else 0

        # Badge height
        badge_height = 24 if show_language_badge and language else 0

        # Image dimensions
        text_width = max_line_len * char_width
        text_height = len(lines) * line_height

        img_width = text_width + line_num_width + (padding * 2)
        img_height = text_height + badge_height + (padding * 2)

        # Minimum size
        img_width = max(img_width, 300)
        img_height = max(img_height, 100)

        # Create image
        img = Image.new('RGB', (img_width, img_height), background_color)
        draw = ImageDraw.Draw(img)

        # Draw language badge
        y_offset = padding
        if show_language_badge and language:
            badge_text = language.upper()
            draw.rectangle(
                [padding, padding, padding + len(badge_text) * 8 + 12, padding + 20],
                fill='#3c3c3c'
            )
            draw.text(
                (padding + 6, padding + 3),
                badge_text,
                font=get_monospace_font(11),
                fill='#cccccc'
            )
            y_offset = padding + badge_height

        # Draw code lines
        for i, line in enumerate(lines):
            y = y_offset + (i * line_height)

            # Line number
            if show_line_numbers:
                line_num = str(i + 1).rjust(len(str(len(lines))))
                draw.text(
                    (padding, y),
                    line_num,
                    font=font,
                    fill=line_number_color
                )

            # Code text
            x = padding + line_num_width
            draw.text((x, y), line, font=font, fill=text_color)

        # Save to bytes
        buffer = io.BytesIO()
        img.save(buffer, 'PNG', optimize=True)
        image_bytes = buffer.getvalue()

        logger.info(f"Rendered code block (simple) to PNG ({len(image_bytes)} bytes)")
        return image_bytes

    except Exception as e:
        raise CodeRenderError(f"Failed to render code (simple): {e}") from e
