"""
Content processing methods for Google Drive sync.

Provides mixin class with methods for processing Mermaid diagrams,
ASCII wireframes, syntax-highlighted code blocks, and local images
before embedding them into Google Docs documents.
"""

from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path
from typing import Any

from ..ascii_renderer import ASCIIRenderError, render_ascii_to_image
from ..code_renderer import CodeRenderError, render_code_to_image
from ..mermaid_api import MermaidAPIError, MermaidCLIError, get_mermaid_url, render_mermaid_diagram

logger = logging.getLogger(__name__)


def _find_text_marker(gdocs_service: Any, doc_id: str, marker_text: str) -> int | None:
    """Find a text marker's start index in a Google Doc.

    Args:
        gdocs_service: GoogleDocsService with docs_service attribute.
        doc_id: Google Doc ID.
        marker_text: Exact marker text to find (e.g. '[ASCII:name]').

    Returns:
        Start index of the marker, or None if not found.
    """
    doc = gdocs_service.docs_service.documents().get(documentId=doc_id).execute()
    for element in doc.get('body', {}).get('content', []):
        if 'paragraph' in element:
            for para_element in element['paragraph'].get('elements', []):
                if 'textRun' in para_element:
                    text = para_element['textRun'].get('content', '')
                    if marker_text in text:
                        start_idx = para_element.get('startIndex', 0)
                        return start_idx + text.find(marker_text)
    return None


def _upload_and_get_url(
    gdrive_service: Any,
    get_or_create_folder: Any,
    png_bytes: bytes,
    name: str,
    folder_id: str,
    folder_cache: dict[str, str],
    delay: float = 0.3,
) -> str:
    """Upload image bytes to Drive and return the public view URL.

    Args:
        gdrive_service: GoogleDriveService instance.
        get_or_create_folder: Callable to create/get a folder.
        png_bytes: Image data.
        name: Filename (without extension).
        folder_id: Parent folder ID.
        folder_cache: Mutable dict with 'id' key for caching folder ID.
        delay: Seconds to wait after upload for Drive processing.

    Returns:
        Public URL string for embedding.
    """
    if not folder_cache.get('id'):
        folder_cache['id'] = get_or_create_folder("Diagram Images", folder_id)

    file_metadata = gdrive_service.upload_image_bytes(
        image_bytes=png_bytes, filename=f"{name}.png",
        folder_id=folder_cache['id'], mime_type='image/png'
    )
    try:
        gdrive_service.set_public_permissions(file_metadata['id'])
    except Exception as e:
        logger.warning(f"  Could not set public permissions: {e}")

    time.sleep(delay)
    logger.info(f"  Uploaded to Drive ({len(png_bytes)} bytes)")
    return f"https://drive.google.com/uc?export=view&id={file_metadata['id']}"


class ProcessorMixin:
    """Mixin providing content processing methods for GoogleDriveSync.

    Expects the host class to provide ``gdocs_service``, ``gdrive_service``,
    and ``get_or_create_folder(name, parent_id)``.
    """

    def _process_mermaid_diagrams(self, doc_id: str, diagrams: list[dict[str, str]], folder_id: str) -> None:
        """Process Mermaid diagrams: render and embed in document.

        Args:
            doc_id: Google Doc ID to embed diagrams into.
            diagrams: List of diagram dicts with 'name' and 'code' keys.
            folder_id: Google Drive folder ID for image storage.
        """
        diagrams_folder = {}
        render_mode = os.environ.get('MERMAID_RENDER_MODE', 'local').lower()

        for diagram in diagrams:
            try:
                diagram_name = diagram['name']
                diagram_code = diagram['code']
                logger.info(f"  Processing {diagram_name}...")

                use_drive_upload = (render_mode == 'local')
                if not use_drive_upload:
                    mermaid_url = get_mermaid_url(diagram_code, format='png', theme='default', background_color='white')
                    if len(mermaid_url) > 2000:
                        use_drive_upload = True
                        logger.info(f"  URL too long ({len(mermaid_url)} bytes) - using Drive upload")
                    else:
                        logger.info(f"  Using direct Mermaid.ink URL ({len(mermaid_url)} bytes)")
                        image_url = mermaid_url

                if use_drive_upload:
                    logger.info("  Rendering locally and uploading to Drive...")
                    png_bytes = render_mermaid_diagram(diagram_code, format='png')
                    image_url = _upload_and_get_url(
                        self.gdrive_service, self.get_or_create_folder,
                        png_bytes, diagram_name, folder_id, diagrams_folder, delay=0.5
                    )

                markers = self.gdocs_service.find_diagram_markers(doc_id)
                matching = [m for m in markers if m['name'] == diagram_name]
                if matching:
                    marker = matching[0]
                    self.gdocs_service.embed_diagram(
                        doc_id=doc_id, diagram_name=diagram_name, image_url=image_url,
                        marker_index=marker['index'], marker_length=marker['length'],
                        width_pt=500, height_pt=350
                    )
                    logger.info(f"  Embedded {diagram_name}")
                else:
                    logger.warning(f"  Marker not found for {diagram_name}")

            except (MermaidAPIError, MermaidCLIError) as e:
                logger.error(f"  Failed to render {diagram_name}: {e}")
            except Exception as e:
                logger.error(f"  Failed to process {diagram_name}: {e}")

    def _process_ascii_codeblocks(self, doc_id: str, ascii_blocks: list[dict[str, str]], folder_id: str) -> None:
        """Process ASCII code blocks: render to PNG and embed in document.

        Args:
            doc_id: Google Doc ID to embed images into.
            ascii_blocks: List of block dicts with 'name' and 'code' keys.
            folder_id: Google Drive folder ID for image storage.
        """
        folder_cache = {}
        for block in ascii_blocks:
            try:
                block_name, block_code = block['name'], block['code']
                logger.info(f"  Processing {block_name}...")

                png_bytes = render_ascii_to_image(
                    text=block_code, font_size=12, padding=15,
                    background_color="#f6f8fa", text_color="#24292e",
                    border_color="#d0d7de", border_width=1
                )
                image_url = _upload_and_get_url(
                    self.gdrive_service, self.get_or_create_folder,
                    png_bytes, block_name, folder_id, folder_cache
                )

                marker_text = f"[ASCII:{block_name}]"
                marker_index = _find_text_marker(self.gdocs_service, doc_id, marker_text)
                if marker_index is not None:
                    self.gdocs_service.embed_diagram(
                        doc_id=doc_id, diagram_name=block_name, image_url=image_url,
                        marker_index=marker_index, marker_length=len(marker_text),
                        width_pt=550, height_pt=400
                    )
                    logger.info(f"  Embedded {block_name}")
                else:
                    logger.warning(f"  Marker not found for {block_name}")

            except ASCIIRenderError as e:
                logger.error(f"  Failed to render {block_name}: {e}")
            except Exception as e:
                logger.error(f"  Failed to process {block_name}: {e}")

    def _process_code_blocks(self, doc_id: str, code_blocks: list[dict[str, str]], folder_id: str) -> None:
        """Process syntax-highlighted code blocks: render to PNG and embed in document.

        Args:
            doc_id: Google Doc ID to embed images into.
            code_blocks: List of block dicts with 'name', 'code', and 'language' keys.
            folder_id: Google Drive folder ID for image storage.
        """
        folder_cache = {}
        for block in code_blocks:
            try:
                block_name, block_code = block['name'], block['code']
                language = block.get('language', '')
                logger.info(f"  Processing {block_name} ({language})...")

                png_bytes = render_code_to_image(
                    code=block_code, language=language,
                    style='monokai', font_size=12, line_numbers=True
                )
                image_url = _upload_and_get_url(
                    self.gdrive_service, self.get_or_create_folder,
                    png_bytes, block_name, folder_id, folder_cache
                )

                marker_text = f"[CODE:{block_name}]"
                marker_index = _find_text_marker(self.gdocs_service, doc_id, marker_text)
                if marker_index is not None:
                    self.gdocs_service.embed_diagram(
                        doc_id=doc_id, diagram_name=block_name, image_url=image_url,
                        marker_index=marker_index, marker_length=len(marker_text),
                        width_pt=550, height_pt=300
                    )
                    logger.info(f"  Embedded {block_name}")
                else:
                    logger.warning(f"  Marker not found for {block_name}")

            except CodeRenderError as e:
                logger.error(f"  Failed to render {block_name}: {e}")
            except Exception as e:
                logger.error(f"  Failed to process {block_name}: {e}")

    def _process_local_images(self, doc_id: str, images: list[dict[str, str]], folder_id: str) -> None:
        """Process local image files: upload to Drive and embed in document.

        Args:
            doc_id: Google Doc ID to embed images into.
            images: List of image dicts with 'name', 'path', and 'display_name' keys.
            folder_id: Google Drive folder ID for image storage.
        """
        images_folder_id = None

        for image in images:
            try:
                image_name = image['name']
                image_path = Path(image['path'])
                display_name = image.get('display_name', image_name)
                logger.info(f"  Processing {display_name}...")

                if not image_path.exists():
                    logger.warning(f"  Image file not found: {image_path}")
                    continue

                with open(image_path, 'rb') as f:
                    image_bytes = f.read()

                suffix = image_path.suffix.lower()
                mime_types = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                              '.gif': 'image/gif', '.webp': 'image/webp'}
                mime_type = mime_types.get(suffix, 'image/png')

                if not images_folder_id:
                    images_folder_id = self.get_or_create_folder("Embedded Images", folder_id)

                file_metadata = self.gdrive_service.upload_image_bytes(
                    image_bytes=image_bytes, filename=f"{display_name}{suffix}",
                    folder_id=images_folder_id, mime_type=mime_type
                )

                try:
                    self.gdrive_service.add_service_account_reader(file_metadata['id'])
                except Exception as e:
                    logger.info(f"  Permission already inherited: {e}")

                try:
                    self.gdrive_service.set_public_permissions(file_metadata['id'])
                except Exception as e:
                    logger.warning(f"  Could not set public permissions: {e}")

                image_url = f"https://drive.google.com/uc?export=view&id={file_metadata['id']}"
                logger.info(f"  Uploaded to Drive ({len(image_bytes)} bytes)")

                markers = self._find_image_markers(doc_id)
                matching = [m for m in markers if m['name'] == image_name]
                if matching:
                    marker = matching[0]
                    self.gdocs_service.embed_diagram(
                        doc_id=doc_id, diagram_name=image_name, image_url=image_url,
                        marker_index=marker['index'], marker_length=marker['length'],
                        width_pt=280, height_pt=175
                    )
                    logger.info(f"  Embedded {display_name}")
                else:
                    logger.warning(f"  Marker not found for {image_name}")

            except Exception as e:
                logger.error(f"  Failed to process {image.get('display_name', image_name)}: {e}")

    def _find_image_markers(self, doc_id: str) -> list[dict[str, Any]]:
        """Find image markers in document ([IMAGE:name]).

        Args:
            doc_id: Google Doc ID to search for markers.

        Returns:
            List of marker dicts with 'name', 'index', and 'length' keys.
        """
        try:
            doc = self.gdocs_service.docs_service.documents().get(documentId=doc_id).execute()
            content = doc.get('body', {}).get('content', [])
            markers = []
            marker_pattern = r'\[IMAGE:(\w+)\]'

            for element in content:
                if 'paragraph' in element:
                    for text_run in element['paragraph'].get('elements', []):
                        if 'textRun' in text_run:
                            text_content = text_run['textRun'].get('content', '')
                            start_index = text_run.get('startIndex', 0)
                            for match in re.finditer(marker_pattern, text_content):
                                markers.append({
                                    'name': match.group(1),
                                    'index': start_index + match.start(),
                                    'length': len(match.group(0))
                                })

            logger.info(f"Found {len(markers)} image markers in {doc_id}")
            return markers
        except Exception as error:
            logger.error(f"Failed to find image markers: {error}")
            return []
