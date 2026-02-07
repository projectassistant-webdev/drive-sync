"""
File conversion utilities for Markdown, CSV, and Mermaid diagrams.

Enhanced with Mermaid diagram extraction, image embedding, and marker replacement.
"""

from __future__ import annotations

import hashlib
import re
import tempfile
from pathlib import Path
from typing import Any, ClassVar


class MarkdownConverter:
    """Convert Markdown files to Google Docs format with Mermaid and image support"""

    @staticmethod
    def extract_mermaid_diagrams(md_content: str) -> tuple[str, list[dict[str, str]]]:
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
    def extract_ascii_codeblocks(md_content: str) -> tuple[str, list[dict[str, str]]]:
        """
        Extract ASCII code blocks (non-mermaid) from markdown and replace with markers.

        ASCII wireframes and code blocks use box-drawing characters that require
        monospace fonts to display correctly. Google Docs doesn't preserve monospace
        formatting, so we render these as PNG images.

        Args:
            md_content: Raw markdown content with ``` code blocks

        Returns:
            Tuple of (modified_content, codeblocks_list)
            - modified_content: Markdown with code blocks replaced by markers
            - codeblocks_list: List of dicts with 'name', 'code', 'hash'

        Example:
            Input:
                ```
                ┌─────────────┐
                │  Hello      │
                └─────────────┘
                ```

            Output:
                Content: "[ASCII:ascii_abc123]"
                Codeblocks: [{'name': 'ascii_abc123', 'code': '┌─────...', 'hash': 'abc123'}]
        """
        codeblocks = []

        def replace_codeblock(match):
            lang = match.group(1) or ''  # Language specifier (if any)
            code_content = match.group(2).strip()

            # Skip if empty or very short
            if not code_content or len(code_content) < 10:
                return match.group(0)

            # Skip non-ASCII code blocks (programming languages)
            # Only render blocks that contain box-drawing chars or look like wireframes
            box_chars = '┌┐└┘─│├┤┬┴┼═║╔╗╚╝╠╣╦╩╬'
            has_box_chars = any(c in code_content for c in box_chars)

            # Also check for ASCII art patterns (multiple consecutive special chars)
            has_ascii_pattern = bool(re.search(r'[│|─\-+]{3,}', code_content))

            # Box-drawing characters are a STRONG signal - if present, it's ASCII art
            # Don't let keyword detection override box-drawing detection
            if has_box_chars:
                # Definitely ASCII art, process it
                pass
            elif has_ascii_pattern:
                # Might be ASCII art, check for code keywords
                code_keywords = ['def ', 'function ', 'class ', 'import ', 'const ', 'let ', 'var ', 'return ']
                looks_like_code = any(kw in code_content.lower() for kw in code_keywords)
                if looks_like_code:
                    return match.group(0)
            else:
                # No ASCII art indicators, skip
                return match.group(0)

            # Generate unique name for code block
            code_hash = hashlib.md5(code_content.encode()).hexdigest()[:8]
            block_name = f"ascii_{code_hash}"

            # Store code block info
            codeblocks.append({
                'name': block_name,
                'code': code_content,
                'hash': code_hash,
                'lang': lang
            })

            # Replace with marker
            return f"\n[ASCII:{block_name}]\n"

        # Match code blocks: ```lang\ncontent``` or ```\ncontent```
        # But NOT ```mermaid blocks (those are handled separately)
        modified_content = re.sub(
            r'```(?!mermaid)(\w*)\n(.*?)```',
            replace_codeblock,
            md_content,
            flags=re.DOTALL
        )

        return modified_content, codeblocks

    @staticmethod
    def extract_syntax_codeblocks(md_content: str) -> tuple[str, list[dict[str, str]]]:
        """
        Extract syntax-highlighted code blocks from markdown and replace with markers.

        These are code blocks with a language specifier (e.g., ```javascript, ```python)
        that should be rendered as PNG images with syntax highlighting.

        Args:
            md_content: Raw markdown content with ``` code blocks

        Returns:
            Tuple of (modified_content, codeblocks_list)
            - modified_content: Markdown with code blocks replaced by markers
            - codeblocks_list: List of dicts with 'name', 'code', 'hash', 'lang'

        Example:
            Input:
                ```javascript
                const x = 1;
                console.log(x);
                ```

            Output:
                Content: "[CODE:code_abc123]"
                Codeblocks: [{'name': 'code_abc123', 'code': 'const x...', 'lang': 'javascript'}]
        """
        codeblocks = []

        # Known programming languages to render as syntax-highlighted images
        SYNTAX_LANGUAGES = {
            'javascript', 'js', 'typescript', 'ts', 'python', 'py', 'java', 'kotlin',
            'swift', 'go', 'rust', 'ruby', 'rb', 'php', 'c', 'cpp', 'csharp', 'cs',
            'sql', 'bash', 'sh', 'shell', 'powershell', 'yaml', 'yml', 'json', 'xml',
            'html', 'css', 'scss', 'sass', 'less', 'graphql', 'dockerfile', 'docker',
            'terraform', 'hcl', 'nginx', 'apache', 'lua', 'perl', 'r', 'scala',
            'groovy', 'elixir', 'erlang', 'clojure', 'haskell', 'ocaml', 'fsharp',
            'dart', 'jsx', 'tsx', 'vue', 'svelte', 'markdown', 'md', 'toml', 'ini',
            'makefile', 'cmake', 'gradle', 'maven', 'npm', 'pip', 'requirements',
        }

        def replace_codeblock(match):
            lang = (match.group(1) or '').lower().strip()
            code_content = match.group(2).strip()

            # Skip if no language specified or not a known language
            if not lang or lang not in SYNTAX_LANGUAGES:
                return match.group(0)

            # Skip if empty or very short
            if not code_content or len(code_content) < 5:
                return match.group(0)

            # Skip ASCII art blocks (those have box-drawing chars)
            box_chars = '┌┐└┘─│├┤┬┴┼═║╔╗╚╝╠╣╦╩╬'
            if any(c in code_content for c in box_chars):
                return match.group(0)

            # Generate unique name for code block
            code_hash = hashlib.md5(code_content.encode()).hexdigest()[:8]
            block_name = f"code_{code_hash}"

            # Store code block info
            codeblocks.append({
                'name': block_name,
                'code': code_content,
                'hash': code_hash,
                'lang': lang
            })

            # Replace with marker
            return f"\n[CODE:{block_name}]\n"

        # Match code blocks with language specifier: ```lang\ncontent```
        # Skip mermaid blocks (handled separately)
        modified_content = re.sub(
            r'```(?!mermaid)(\w+)\n(.*?)```',
            replace_codeblock,
            md_content,
            flags=re.DOTALL
        )

        return modified_content, codeblocks

    @staticmethod
    def extract_local_images(md_content: str, source_file: Path) -> tuple[str, list[dict[str, str]]]:
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
        extract_images: bool = True,
        extract_ascii: bool = True,
        extract_code: bool = True
    ) -> dict[str, Any]:
        """
        Prepare markdown file for upload with optional code formatting, diagram and image extraction.

        Args:
            md_file: Path to markdown file
            format_code: Whether to apply code formatting (default: True)
            extract_diagrams: Whether to extract Mermaid diagrams (default: True)
            extract_images: Whether to extract local image references (default: True)
            extract_ascii: Whether to extract ASCII code blocks as images (default: True)
            extract_code: Whether to extract syntax-highlighted code blocks as images (default: True)

        Returns:
            Dictionary with:
            - name: Document name
            - mimeType: MIME type
            - description: File description
            - temp_file: Path to temporary processed file (if processing was done)
            - diagrams: List of extracted diagrams (if any)
            - images: List of extracted image references (if any)
            - ascii_blocks: List of extracted ASCII code blocks (if any)
            - code_blocks: List of extracted syntax code blocks (if any)
        """
        md_file = Path(md_file)

        # Read markdown content
        with open(md_file, encoding='utf-8') as f:
            md_content = f.read()

        diagrams = []
        images = []
        ascii_blocks = []
        code_blocks = []

        # Extract Mermaid diagrams first (before code formatting)
        if extract_diagrams:
            md_content, diagrams = MarkdownConverter.extract_mermaid_diagrams(md_content)

        # Extract syntax-highlighted code blocks (before ASCII extraction to avoid conflicts)
        if extract_code:
            md_content, code_blocks = MarkdownConverter.extract_syntax_codeblocks(md_content)

        # Extract ASCII code blocks (wireframes, ASCII art) - renders as images
        if extract_ascii:
            md_content, ascii_blocks = MarkdownConverter.extract_ascii_codeblocks(md_content)

        # Extract local image references (before code formatting converts backticks)
        if extract_images:
            md_content, images = MarkdownConverter.extract_local_images(md_content, md_file)

        # Apply code formatting
        if format_code:
            md_content = MarkdownConverter.preprocess_markdown_for_google_docs(md_content)

        # Create temporary file with processed content
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as temp_file:
            temp_file.write(md_content)
            temp_file_name = temp_file.name

        return {
            'name': md_file.stem,
            'mimeType': 'text/markdown',
            'description': f'Converted from {md_file.name}',
            'temp_file': temp_file_name,
            'diagrams': diagrams,
            'images': images,
            'ascii_blocks': ascii_blocks,
            'code_blocks': code_blocks
        }

    @staticmethod
    def get_conversion_mimetype() -> str:
        """Get Google Docs MIME type for conversion"""
        return 'application/vnd.google-apps.document'


class CSVConverter:
    """Convert CSV files to Google Sheets format"""

    @staticmethod
    def prepare_for_upload(csv_file: Path) -> dict[str, str]:
        """Prepare CSV file for upload.

        Args:
            csv_file: Path to CSV file.

        Returns:
            Dictionary with file metadata.
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
    def prepare_for_upload(pdf_file: Path) -> dict[str, str]:
        """Prepare PDF file for upload (no conversion needed).

        Args:
            pdf_file: Path to PDF file.

        Returns:
            Dictionary with file metadata.
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

    CONVERTERS: ClassVar[dict] = {
        '.md': MarkdownConverter,
        '.markdown': MarkdownConverter,
        '.csv': CSVConverter,
        '.pdf': PDFConverter,
    }

    # Files to silently ignore (not count as errors)
    IGNORED_FILES: ClassVar[set] = {
        '.gitkeep',
        '.gitignore',
        '.DS_Store',
        'Thumbs.db',
    }

    # Extensions to silently ignore
    IGNORED_EXTENSIONS: ClassVar[set] = {
        '.mp4', '.mov', '.avi', '.mkv', '.wmv',  # Video
        '.mp3', '.wav', '.flac', '.aac',          # Audio
        '.zip', '.tar', '.gz', '.rar', '.7z',     # Archives
        '.exe', '.dll', '.so', '.dylib',          # Binaries
        '.pyc', '.pyo', '.class',                 # Compiled
    }

    @classmethod
    def should_ignore(cls, file_path: Path) -> bool:
        """Check if file should be silently ignored.

        Args:
            file_path: Path to the file to check.

        Returns:
            True if the file should be silently skipped during sync.
        """
        filename = file_path.name.lower()
        extension = file_path.suffix.lower()

        if filename in cls.IGNORED_FILES or file_path.name in cls.IGNORED_FILES:
            return True
        return extension in cls.IGNORED_EXTENSIONS

    @classmethod
    def get_converter(cls, file_path: Path) -> type[MarkdownConverter] | type[CSVConverter] | type[PDFConverter]:
        """Get appropriate converter for file type.

        Args:
            file_path: Path to file.

        Returns:
            Converter class for the given file type.

        Raises:
            ValueError: If file type is not supported.
        """
        suffix = file_path.suffix.lower()
        converter = cls.CONVERTERS.get(suffix)

        if converter is None:
            raise ValueError(
                f"Unsupported file type: {suffix}\n"
                f"Supported types: {', '.join(cls.CONVERTERS.keys())}"
            )

        return converter
