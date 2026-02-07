"""
ASCII code block to PNG image renderer using Pillow.

Converts ASCII art and code blocks to PNG images with monospace fonts
for proper display in Google Docs.
"""

from __future__ import annotations

import hashlib
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

try:
    from PIL import Image, ImageDraw, ImageFont
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False

logger = logging.getLogger(__name__)


class ASCIIRenderError(Exception):
    """Exception raised when ASCII rendering fails"""
    pass


def get_monospace_font(size: int = 14) -> Any:
    """Get a monospace font for rendering ASCII art.

    Tries several common monospace fonts in order of preference.

    Args:
        size: Font size in points.

    Returns:
        PIL ImageFont object.
    """
    # List of monospace fonts to try (in order of preference)
    font_paths = [
        # DejaVu Sans Mono (installed in Docker via fonts-dejavu-core)
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        # Liberation Mono (installed in Docker via fonts-liberation)
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
        # macOS fonts
        "/System/Library/Fonts/Menlo.ttc",
        "/System/Library/Fonts/Monaco.ttf",
        "/Library/Fonts/Courier New.ttf",
        # Linux alternatives
        "/usr/share/fonts/truetype/freefont/FreeMono.ttf",
        "/usr/share/fonts/truetype/ubuntu/UbuntuMono-R.ttf",
    ]

    for font_path in font_paths:
        if os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, size)
            except Exception as e:
                logger.debug(f"Could not load font {font_path}: {e}")
                continue

    # Fallback to default (non-proportional) font
    logger.warning("No monospace font found, using default font")
    return ImageFont.load_default()


def render_ascii_to_image(
    text: str,
    font_size: int = 14,
    padding: int = 20,
    background_color: str = "#f8f9fa",
    text_color: str = "#24292e",
    border_color: str = "#e1e4e8",
    border_width: int = 1,
    line_height_multiplier: float = 1.2
) -> bytes:
    """
    Render ASCII text as a PNG image with monospace font.

    Args:
        text: The ASCII text to render
        font_size: Font size in points (default: 14)
        padding: Padding around text in pixels (default: 20)
        background_color: Background color (default: light gray)
        text_color: Text color (default: dark gray)
        border_color: Border color (default: light border)
        border_width: Border width in pixels (default: 1)
        line_height_multiplier: Line height as multiplier of font size

    Returns:
        PNG image as bytes

    Raises:
        ASCIIRenderError: If rendering fails
    """
    if not PILLOW_AVAILABLE:
        raise ASCIIRenderError("Pillow is not installed")

    try:
        # Get monospace font
        font = get_monospace_font(font_size)

        # Split text into lines
        lines = text.split('\n')

        # Calculate dimensions
        # Use a test character to get consistent metrics
        test_char = 'M'  # Wide character for measurement
        bbox = font.getbbox(test_char)
        char_width = bbox[2] - bbox[0]
        char_height = bbox[3] - bbox[1]
        line_height = int(char_height * line_height_multiplier)

        # Find max line length (in characters)
        max_chars = max(len(line) for line in lines) if lines else 0

        # Calculate image dimensions
        text_width = max_chars * char_width
        text_height = len(lines) * line_height

        img_width = text_width + (padding * 2) + (border_width * 2)
        img_height = text_height + (padding * 2) + (border_width * 2)

        # Ensure minimum size
        img_width = max(img_width, 200)
        img_height = max(img_height, 50)

        # Create image with border
        img = Image.new('RGB', (img_width, img_height), border_color)

        # Create inner rectangle for background
        inner_img = Image.new(
            'RGB',
            (img_width - border_width * 2, img_height - border_width * 2),
            background_color
        )
        img.paste(inner_img, (border_width, border_width))

        # Create drawing context
        draw = ImageDraw.Draw(img)

        # Draw each line of text
        y = padding + border_width
        for line in lines:
            draw.text(
                (padding + border_width, y),
                line,
                font=font,
                fill=text_color
            )
            y += line_height

        # Save to bytes
        temp_dir = Path(tempfile.gettempdir()) / "ascii_render"
        temp_dir.mkdir(exist_ok=True)

        content_hash = hashlib.md5(text.encode()).hexdigest()[:8]
        output_path = temp_dir / f"ascii_{content_hash}.png"

        img.save(output_path, 'PNG', optimize=True)

        with open(output_path, 'rb') as f:
            image_bytes = f.read()

        logger.info(f"Rendered ASCII art to PNG ({len(image_bytes)} bytes)")
        return image_bytes

    except Exception as e:
        raise ASCIIRenderError(f"Failed to render ASCII to image: {e}") from e
