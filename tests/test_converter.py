"""
Tests for file conversion utilities.

Tests Markdown processing, Mermaid extraction, image extraction,
and file type detection.
"""

import pytest
import tempfile
from pathlib import Path
from src.drive_sync.converter import (
    MarkdownConverter,
    CSVConverter,
    PDFConverter,
    FileTypeDetector
)


class TestMermaidExtraction:
    """Test Mermaid diagram extraction from markdown."""

    def test_extract_single_diagram(self):
        """Test extracting a single Mermaid diagram."""
        md_content = """# Header

Some text here.

```mermaid
graph TD
    A[Start] --> B[End]
```

More text after.
"""
        modified, diagrams = MarkdownConverter.extract_mermaid_diagrams(md_content)

        assert len(diagrams) == 1
        assert 'graph TD' in diagrams[0]['code']
        assert 'A[Start] --> B[End]' in diagrams[0]['code']
        assert diagrams[0]['name'].startswith('mermaid_')
        assert '[DIAGRAM:' in modified
        assert '```mermaid' not in modified

    def test_extract_multiple_diagrams(self):
        """Test extracting multiple Mermaid diagrams."""
        md_content = """# Doc with multiple diagrams

```mermaid
graph LR
    A --> B
```

Some text between.

```mermaid
sequenceDiagram
    Alice->>Bob: Hello
```
"""
        modified, diagrams = MarkdownConverter.extract_mermaid_diagrams(md_content)

        assert len(diagrams) == 2
        assert 'graph LR' in diagrams[0]['code']
        assert 'sequenceDiagram' in diagrams[1]['code']
        assert modified.count('[DIAGRAM:') == 2

    def test_no_mermaid_diagrams(self):
        """Test content with no Mermaid diagrams."""
        md_content = """# Just Text

Regular markdown without any diagrams.

```python
print("not mermaid")
```
"""
        modified, diagrams = MarkdownConverter.extract_mermaid_diagrams(md_content)

        assert len(diagrams) == 0
        assert '```python' in modified  # Other code blocks preserved

    def test_diagram_hash_uniqueness(self):
        """Test that identical diagrams get same hash, different diagrams get different hash."""
        md_content = """
```mermaid
graph TD
    A --> B
```

```mermaid
graph TD
    A --> B
```

```mermaid
graph TD
    C --> D
```
"""
        _, diagrams = MarkdownConverter.extract_mermaid_diagrams(md_content)

        assert len(diagrams) == 3
        # First two identical diagrams should have same hash
        assert diagrams[0]['hash'] == diagrams[1]['hash']
        # Third different diagram should have different hash
        assert diagrams[0]['hash'] != diagrams[2]['hash']


class TestCodeBlockFormatting:
    """Test code block preprocessing for Google Docs."""

    def test_format_code_block_with_language(self):
        """Test formatting fenced code blocks with language specifier."""
        md_content = """
```python
def hello():
    print("world")
```
"""
        result = MarkdownConverter.preprocess_markdown_for_google_docs(md_content)

        assert '═══ CODE (PYTHON) ═══' in result
        assert 'def hello():' in result
        assert '```python' not in result

    def test_format_code_block_without_language(self):
        """Test formatting fenced code blocks without language."""
        md_content = """
```
some code here
```
"""
        result = MarkdownConverter.preprocess_markdown_for_google_docs(md_content)

        assert '═══ CODE ═══' in result
        assert 'some code here' in result

    def test_inline_code_formatting(self):
        """Test inline code gets wrapped with angle brackets."""
        md_content = "Use the `print()` function to output text."
        result = MarkdownConverter.preprocess_markdown_for_google_docs(md_content)

        assert '⟨ print() ⟩' in result
        assert '`print()`' not in result

    def test_mermaid_blocks_not_formatted_as_code(self):
        """Test that Mermaid blocks are NOT wrapped with CODE markers.

        Note: In the actual workflow, extract_mermaid_diagrams() is called
        BEFORE preprocess_markdown_for_google_docs(), so mermaid blocks are
        already replaced with [DIAGRAM:...] markers by the time preprocessing
        runs. This test verifies the code block formatter skips mermaid.
        """
        md_content = """
```mermaid
graph TD
    A --> B
```
"""
        result = MarkdownConverter.preprocess_markdown_for_google_docs(md_content)

        # Mermaid should NOT be wrapped with CODE markers
        assert '═══ CODE (MERMAID)' not in result
        # Note: inline backtick processing may affect the block, but that's OK
        # because in real usage, diagrams are extracted first


class TestImageExtraction:
    """Test local image extraction from markdown."""

    def test_extract_standard_markdown_image(self, tmp_path):
        """Test extracting standard markdown image references."""
        # Create a test image file
        image_file = tmp_path / "test.png"
        image_file.write_bytes(b'PNG fake image data')

        # Create markdown file
        md_file = tmp_path / "doc.md"
        md_content = f"![Alt text](test.png)"

        modified, images = MarkdownConverter.extract_local_images(md_content, md_file)

        assert len(images) == 1
        assert images[0]['alt'] == 'Alt text'
        assert 'test.png' in images[0]['path']
        assert '[IMAGE:' in modified

    def test_skip_url_images(self, tmp_path):
        """Test that URL images are not extracted."""
        md_file = tmp_path / "doc.md"
        md_content = "![Logo](https://example.com/logo.png)"

        modified, images = MarkdownConverter.extract_local_images(md_content, md_file)

        assert len(images) == 0
        assert '![Logo](https://example.com/logo.png)' in modified

    def test_skip_nonexistent_images(self, tmp_path):
        """Test that references to nonexistent images are preserved."""
        md_file = tmp_path / "doc.md"
        md_content = "![Missing](does_not_exist.png)"

        modified, images = MarkdownConverter.extract_local_images(md_content, md_file)

        assert len(images) == 0
        assert '![Missing](does_not_exist.png)' in modified

    def test_inline_code_image_reference(self, tmp_path):
        """Test extracting inline code image references like `screenshot.png`."""
        # Create image in screenshots subdirectory
        screenshots_dir = tmp_path / "screenshots"
        screenshots_dir.mkdir()
        image_file = screenshots_dir / "dashboard.png"
        image_file.write_bytes(b'PNG fake')

        md_file = tmp_path / "doc.md"
        md_content = "See the screenshot: `dashboard.png`"

        modified, images = MarkdownConverter.extract_local_images(md_content, md_file)

        assert len(images) == 1
        assert images[0]['display_name'] == 'dashboard'
        assert '[IMAGE:' in modified


class TestFileTypeDetector:
    """Test file type detection and converter selection."""

    def test_markdown_detection(self):
        """Test detection of Markdown files."""
        converter = FileTypeDetector.get_converter(Path("test.md"))
        assert converter == MarkdownConverter

        converter = FileTypeDetector.get_converter(Path("test.markdown"))
        assert converter == MarkdownConverter

    def test_csv_detection(self):
        """Test detection of CSV files."""
        converter = FileTypeDetector.get_converter(Path("data.csv"))
        assert converter == CSVConverter

    def test_pdf_detection(self):
        """Test detection of PDF files."""
        converter = FileTypeDetector.get_converter(Path("document.pdf"))
        assert converter == PDFConverter

    def test_unsupported_file_type(self):
        """Test that unsupported file types raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            FileTypeDetector.get_converter(Path("image.jpg"))

        assert "Unsupported file type" in str(exc_info.value)
        assert ".jpg" in str(exc_info.value)

    def test_case_insensitive_extension(self):
        """Test that extension detection is case-insensitive."""
        converter = FileTypeDetector.get_converter(Path("TEST.MD"))
        assert converter == MarkdownConverter

        converter = FileTypeDetector.get_converter(Path("data.CSV"))
        assert converter == CSVConverter


class TestIgnoredFiles:
    """Test file ignore functionality."""

    def test_gitkeep_ignored(self):
        """Test that .gitkeep files are ignored."""
        assert FileTypeDetector.should_ignore(Path(".gitkeep")) is True
        assert FileTypeDetector.should_ignore(Path("subdir/.gitkeep")) is True

    def test_ds_store_ignored(self):
        """Test that .DS_Store files are ignored."""
        assert FileTypeDetector.should_ignore(Path(".DS_Store")) is True

    def test_video_files_ignored(self):
        """Test that video files are ignored."""
        assert FileTypeDetector.should_ignore(Path("video.mp4")) is True
        assert FileTypeDetector.should_ignore(Path("clip.mov")) is True
        assert FileTypeDetector.should_ignore(Path("movie.avi")) is True

    def test_audio_files_ignored(self):
        """Test that audio files are ignored."""
        assert FileTypeDetector.should_ignore(Path("song.mp3")) is True
        assert FileTypeDetector.should_ignore(Path("audio.wav")) is True

    def test_archive_files_ignored(self):
        """Test that archive files are ignored."""
        assert FileTypeDetector.should_ignore(Path("backup.zip")) is True
        assert FileTypeDetector.should_ignore(Path("data.tar.gz")) is True

    def test_compiled_files_ignored(self):
        """Test that compiled files are ignored."""
        assert FileTypeDetector.should_ignore(Path("module.pyc")) is True
        assert FileTypeDetector.should_ignore(Path("App.class")) is True

    def test_markdown_not_ignored(self):
        """Test that markdown files are NOT ignored."""
        assert FileTypeDetector.should_ignore(Path("readme.md")) is False
        assert FileTypeDetector.should_ignore(Path("docs/guide.md")) is False

    def test_csv_not_ignored(self):
        """Test that CSV files are NOT ignored."""
        assert FileTypeDetector.should_ignore(Path("data.csv")) is False

    def test_case_insensitive_ignore(self):
        """Test that ignore is case-insensitive for extensions."""
        assert FileTypeDetector.should_ignore(Path("video.MP4")) is True
        assert FileTypeDetector.should_ignore(Path("AUDIO.WAV")) is True


class TestConverterMimeTypes:
    """Test MIME type handling for converters."""

    def test_markdown_mime_types(self):
        """Test Markdown converter MIME types."""
        assert MarkdownConverter.get_conversion_mimetype() == 'application/vnd.google-apps.document'

    def test_csv_mime_types(self):
        """Test CSV converter MIME types."""
        assert CSVConverter.get_conversion_mimetype() == 'application/vnd.google-apps.spreadsheet'

    def test_pdf_mime_types(self):
        """Test PDF converter MIME types."""
        assert PDFConverter.get_conversion_mimetype() == 'application/pdf'


class TestPrepareForUpload:
    """Test the prepare_for_upload workflow."""

    def test_prepare_markdown_file(self, tmp_path):
        """Test preparing a markdown file for upload."""
        # Create test markdown file
        md_file = tmp_path / "test_doc.md"
        md_file.write_text("""# Test Document

Some content with `inline code`.

```mermaid
graph TD
    A --> B
```
""")

        result = MarkdownConverter.prepare_for_upload(md_file)

        assert result['name'] == 'test_doc'
        assert result['mimeType'] == 'text/markdown'
        assert 'temp_file' in result
        assert len(result['diagrams']) == 1

        # Verify temp file content
        with open(result['temp_file'], 'r') as f:
            content = f.read()
            assert '⟨ inline code ⟩' in content
            assert '[DIAGRAM:' in content

    def test_prepare_csv_file(self, tmp_path):
        """Test preparing a CSV file for upload."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("a,b,c\n1,2,3")

        result = CSVConverter.prepare_for_upload(csv_file)

        assert result['name'] == 'data'
        assert result['mimeType'] == 'text/csv'

    def test_prepare_pdf_file(self, tmp_path):
        """Test preparing a PDF file for upload."""
        pdf_file = tmp_path / "document.pdf"
        pdf_file.write_bytes(b'%PDF-1.4 fake pdf')

        result = PDFConverter.prepare_for_upload(pdf_file)

        assert result['name'] == 'document.pdf'  # PDF keeps extension
        assert result['mimeType'] == 'application/pdf'
