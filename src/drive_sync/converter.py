"""
File conversion utilities for Markdown, CSV, and Mermaid diagrams.

Enhanced with Mermaid diagram extraction, image embedding, and marker replacement.
"""

import re
import tempfile
import hashlib
from pathlib import Path
from typing import Optional, List, Dict, Tuple


class MarkdownConverter:
    """Convert Markdown files to Google Docs format with Mermaid and image support"""

    @staticmethod
    def extract_mermaid_diagrams(md_content: str) -> Tuple[str, List[Dict[str, str]]]:
        """
        Extract Mermaid diagrams from markdown and replace with markers.

        Args:
            md_content: Raw markdown content with ```mermaid blocks

        Returns:
            Tuple of (modified_content, diagrams_list)
            - modified_content: Markdown with diagrams replaced by markers
            - diagrams_list: List of dicts with 'name', 'code', 'hash'

        Example:
            Input:
                ```mermaid
                graph TD
                    A --> B
                ```

            Output:
                Content: "<!-- DIAGRAM: mermaid_abc123 -->"
                Diagrams: [{'name': 'mermaid_abc123', 'code': 'graph TD...', 'hash': 'abc123'}]
        """
        diagrams = []
        diagram_counter = 0

        def replace_mermaid(match):
            nonlocal diagram_counter
            diagram_code = match.group(1).strip()

            # Generate unique name for diagram
            code_hash = hashlib.md5(diagram_code.encode()).hexdigest()[:8]
            diagram_name = f"mermaid_{code_hash}"

            # Store diagram info
            diagrams.append({
                'name': diagram_name,
                'code': diagram_code,
                'hash': code_hash
            })

            # Replace with visible marker that Google Docs will preserve
            # Using a format that's easy to find but clearly a placeholder
            diagram_counter += 1
            return f"\n[DIAGRAM:{diagram_name}]\n"

        # Replace ```mermaid blocks with markers
        modified_content = re.sub(
            r'```mermaid\n(.*?)```',
            replace_mermaid,
            md_content,
            flags=re.DOTALL
        )

        return modified_content, diagrams

    @staticmethod
    def extract_local_images(md_content: str, source_file: Path) -> Tuple[str, List[Dict[str, str]]]:
        """
        Extract local image references from markdown and replace with markers.

        Handles both:
        - Standard markdown: ![alt](path/to/image.png)
        - Inline code references: `image.png` or ⟨ image.png ⟩

        Args:
            md_content: Raw markdown content with image references
            source_file: Path to the source markdown file (for resolving relative paths)

        Returns:
            Tuple of (modified_content, images_list)
            - modified_content: Markdown with images replaced by markers
            - images_list: List of dicts with 'name', 'path', 'marker'
        """
        images = []
        source_dir = source_file.parent

        # Pattern 1: Standard markdown images ![alt](path)
        def replace_md_image(match):
            alt_text = match.group(1)
            image_path = match.group(2)

            # Skip URLs (http/https)
            if image_path.startswith(('http://', 'https://', '//')):
                return match.group(0)

            # Resolve relative path
            full_path = (source_dir / image_path).resolve()

            # Only process if file exists and is an image
            if full_path.exists() and full_path.suffix.lower() in ['.png', '.jpg', '.jpeg', '.gif', '.webp']:
                # Create unique marker name based on filename
                image_name = full_path.stem
                marker_name = f"image_{hashlib.md5(str(full_path).encode()).hexdigest()[:8]}"

                images.append({
                    'name': marker_name,
                    'display_name': image_name,
                    'path': str(full_path),
                    'alt': alt_text
                })

                return f"\n[IMAGE:{marker_name}]\n"

            return match.group(0)

        # Replace standard markdown images
        modified_content = re.sub(
            r'!\[([^\]]*)\]\(([^)]+)\)',
            replace_md_image,
            md_content
        )

        # Pattern 2: Inline code image references like `cherry-01-dashboard.png`
        # These get converted to ⟨ cherry-01-dashboard.png ⟩ by preprocess
        # We need to detect them BEFORE preprocessing
        def replace_inline_image_ref(match):
            filename = match.group(1).strip()

            # Check if it's an image file reference
            if not filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                return match.group(0)

            # Try to find the image in common locations
            search_paths = [
                source_dir / filename,
                source_dir / 'screenshots' / filename,
                source_dir / 'images' / filename,
                source_dir.parent / 'screenshots' / filename,
                source_dir.parent / 'images' / filename,
                source_dir.parent / 'scope' / 'screenshots' / filename,
            ]

            for search_path in search_paths:
                full_path = search_path.resolve()
                if full_path.exists():
                    image_name = full_path.stem
                    marker_name = f"image_{hashlib.md5(str(full_path).encode()).hexdigest()[:8]}"

                    # Check if we already have this image
                    existing = [img for img in images if img['path'] == str(full_path)]
                    if existing:
                        marker_name = existing[0]['name']
                    else:
                        images.append({
                            'name': marker_name,
                            'display_name': image_name,
                            'path': str(full_path),
                            'alt': filename
                        })

                    return f"[IMAGE:{marker_name}]"

            # Image not found, leave original
            return match.group(0)

        # Replace inline code image references (before they become ⟨ ⟩ format)
        modified_content = re.sub(
            r'`([^`]+\.(?:png|jpg|jpeg|gif|webp))`',
            replace_inline_image_ref,
            modified_content,
            flags=re.IGNORECASE
        )

        return modified_content, images

    @staticmethod
    def preprocess_markdown_for_google_docs(md_content: str) -> str:
        """
        Preprocess markdown to make code blocks more readable in Google Docs.
        Wraps code blocks with visual markers that Google Docs will preserve.

        Args:
            md_content: Raw markdown content

        Returns:
            Processed markdown content with formatted code blocks
        """
        # Process fenced code blocks (```language ... ```) - but NOT mermaid
        def replace_code_block(match):
            language = match.group(1) or ''

            # Skip mermaid blocks (handled separately)
            if language.lower() == 'mermaid':
                return match.group(0)

            code = match.group(2)

            # Add visual markers around code blocks
            header = f"═══ CODE ({language.upper()}) ═══" if language else "═══ CODE ═══"
            footer = "═" * len(header)

            # Indent code slightly for better visibility
            indented_code = '\n'.join('    ' + line for line in code.split('\n'))

            return f"\n{header}\n{indented_code}\n{footer}\n"

        # Replace non-mermaid code blocks
        md_content = re.sub(
            r'```(\w+)?\n(.*?)```',
            replace_code_block,
            md_content,
            flags=re.DOTALL
        )

        # Process inline code (`code`)
        md_content = re.sub(
            r'`([^`]+)`',
            r'⟨ \1 ⟩',
            md_content
        )

        return md_content

    @staticmethod
    def prepare_for_upload(
        md_file: Path,
        format_code: bool = True,
        extract_diagrams: bool = True,
        extract_images: bool = True
    ) -> dict:
        """
        Prepare markdown file for upload with optional code formatting, diagram and image extraction.

        Args:
            md_file: Path to markdown file
            format_code: Whether to apply code formatting (default: True)
            extract_diagrams: Whether to extract Mermaid diagrams (default: True)
            extract_images: Whether to extract local image references (default: True)

        Returns:
            Dictionary with:
            - name: Document name
            - mimeType: MIME type
            - description: File description
            - temp_file: Path to temporary processed file (if processing was done)
            - diagrams: List of extracted diagrams (if any)
            - images: List of extracted image references (if any)
        """
        md_file = Path(md_file)

        # Read markdown content
        with open(md_file, 'r', encoding='utf-8') as f:
            md_content = f.read()

        diagrams = []
        images = []

        # Extract Mermaid diagrams first (before code formatting)
        if extract_diagrams:
            md_content, diagrams = MarkdownConverter.extract_mermaid_diagrams(md_content)

        # Extract local image references (before code formatting converts backticks)
        if extract_images:
            md_content, images = MarkdownConverter.extract_local_images(md_content, md_file)

        # Apply code formatting
        if format_code:
            md_content = MarkdownConverter.preprocess_markdown_for_google_docs(md_content)

        # Create temporary file with processed content
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8')
        temp_file.write(md_content)
        temp_file.close()

        return {
            'name': md_file.stem,
            'mimeType': 'text/markdown',
            'description': f'Converted from {md_file.name}',
            'temp_file': temp_file.name,
            'diagrams': diagrams,
            'images': images
        }

    @staticmethod
    def get_conversion_mimetype() -> str:
        """Get Google Docs MIME type for conversion"""
        return 'application/vnd.google-apps.document'


class CSVConverter:
    """Convert CSV files to Google Sheets format"""

    @staticmethod
    def prepare_for_upload(csv_file: Path) -> dict:
        """
        Prepare CSV file for upload

        Args:
            csv_file: Path to CSV file

        Returns:
            Dictionary with file metadata
        """
        return {
            'name': csv_file.stem,
            'mimeType': 'text/csv',
            'description': f'Converted from {csv_file.name}'
        }

    @staticmethod
    def get_conversion_mimetype() -> str:
        """Get Google Sheets MIME type for conversion"""
        return 'application/vnd.google-apps.spreadsheet'


class PDFConverter:
    """Handle PDF files - upload directly to Google Drive (no conversion)"""

    @staticmethod
    def prepare_for_upload(pdf_file: Path) -> dict:
        """
        Prepare PDF file for upload (no conversion needed)

        Args:
            pdf_file: Path to PDF file

        Returns:
            Dictionary with file metadata
        """
        return {
            'name': pdf_file.name,  # Keep full filename including .pdf
            'mimeType': 'application/pdf',
            'description': f'Uploaded from {pdf_file.name}'
        }

    @staticmethod
    def get_conversion_mimetype() -> str:
        """PDFs are not converted - they stay as PDFs in Drive"""
        return 'application/pdf'


class FileTypeDetector:
    """Detect file types and choose appropriate converter"""

    CONVERTERS = {
        '.md': MarkdownConverter,
        '.markdown': MarkdownConverter,
        '.csv': CSVConverter,
        '.pdf': PDFConverter,
    }

    @classmethod
    def get_converter(cls, file_path: Path):
        """
        Get appropriate converter for file type

        Args:
            file_path: Path to file

        Returns:
            Converter class or None if unsupported

        Raises:
            ValueError: If file type is not supported
        """
        suffix = file_path.suffix.lower()
        converter = cls.CONVERTERS.get(suffix)

        if converter is None:
            raise ValueError(
                f"Unsupported file type: {suffix}\n"
                f"Supported types: {', '.join(cls.CONVERTERS.keys())}"
            )

        return converter
