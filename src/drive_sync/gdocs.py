"""
Google Docs Tool - Enhanced Google Docs operations for diagram embedding.

Provides:
- Document creation and updates
- Diagram marker detection (<!-- DIAGRAM: name -->)
- Image embedding at marker positions
- Professional styling
"""

import logging
import re
from typing import Dict, Any, List, Optional
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2 import service_account

from .utils import slugify_heading, get_unique_slug


logger = logging.getLogger(__name__)


SCOPES = [
    'https://www.googleapis.com/auth/documents',
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/drive.file'
]


class GoogleDocsError(Exception):
    """Base exception for Google Docs operations"""
    pass


class GoogleDocsService:
    """
    Google Docs service wrapper with diagram embedding support.
    """

    def __init__(self, credentials_path: str):
        """
        Initialize Google Docs service.

        Args:
            credentials_path: Path to service account credentials JSON
        """
        self.credentials_path = credentials_path
        self.docs_service = None
        self.drive_service = None
        self._authenticate()

    def _authenticate(self):
        """Authenticate with Google Docs and Drive APIs"""
        try:
            if not Path(self.credentials_path).exists():
                raise GoogleDocsError(
                    f"Credentials not found: {self.credentials_path}"
                )

            credentials = service_account.Credentials.from_service_account_file(
                self.credentials_path,
                scopes=SCOPES
            )

            self.docs_service = build('docs', 'v1', credentials=credentials)
            self.drive_service = build('drive', 'v3', credentials=credentials)
            logger.info("Authenticated with Google Docs API")

        except Exception as e:
            logger.error(f"Authentication failed: {str(e)}")
            raise GoogleDocsError(f"Authentication failed: {str(e)}")

    def find_diagram_markers(self, doc_id: str) -> List[Dict[str, Any]]:
        """
        Find diagram markers in document ([DIAGRAM:name]).

        Args:
            doc_id: Document ID

        Returns:
            List[Dict]: List of marker locations with name and index
        """
        try:
            doc = self.docs_service.documents().get(documentId=doc_id).execute()
            content = doc.get('body', {}).get('content', [])
            markers = []

            # Pattern for diagram markers (visible text format that survives conversion)
            marker_pattern = r'\[DIAGRAM:(\w+)\]'

            # Search through content
            for element in content:
                if 'paragraph' in element:
                    paragraph = element['paragraph']
                    for text_run in paragraph.get('elements', []):
                        if 'textRun' in text_run:
                            text_content = text_run['textRun'].get('content', '')
                            start_index = text_run.get('startIndex', 0)

                            # Find all markers in this text run
                            for match in re.finditer(marker_pattern, text_content):
                                diagram_name = match.group(1)
                                marker_offset = match.start()
                                marker_index = start_index + marker_offset

                                markers.append({
                                    'name': diagram_name,
                                    'index': marker_index,
                                    'length': len(match.group(0))
                                })

            logger.info(f"Found {len(markers)} diagram markers in {doc_id}")
            return markers

        except HttpError as error:
            logger.error(f"Failed to find markers: {error}")
            return []

    def embed_diagram(
        self,
        doc_id: str,
        diagram_name: str,
        image_url: str,
        marker_index: int,
        marker_length: int,
        width_pt: int = 500,
        height_pt: int = 350
    ) -> None:
        """
        Embed diagram image at marker location.

        Args:
            doc_id: Document ID
            diagram_name: Name of the diagram
            image_url: URL of the image to embed
            marker_index: Index of the marker in the document
            marker_length: Length of the marker text
            width_pt: Image width in points
            height_pt: Image height in points

        Raises:
            GoogleDocsError: If embedding fails
        """
        try:
            # Build batch update requests
            requests = [
                # Delete the marker text
                {
                    'deleteContentRange': {
                        'range': {
                            'startIndex': marker_index,
                            'endIndex': marker_index + marker_length
                        }
                    }
                },
                # Insert image at marker location
                {
                    'insertInlineImage': {
                        'location': {'index': marker_index},
                        'uri': image_url,
                        'objectSize': {
                            'height': {'magnitude': height_pt, 'unit': 'PT'},
                            'width': {'magnitude': width_pt, 'unit': 'PT'}
                        }
                    }
                }
            ]

            self.docs_service.documents().batchUpdate(
                documentId=doc_id,
                body={'requests': requests}
            ).execute()

            logger.info(f"Embedded '{diagram_name}' at index {marker_index}")

        except HttpError as error:
            logger.error(f"Failed to embed diagram: {error}")
            raise GoogleDocsError(f"Failed to embed diagram: {error}")

    @staticmethod
    def _parse_headings(document: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """
        Parse headings from Google Docs document structure.

        Extracts heading text, level, and headingId (NOT bookmarkId) from document.
        Generates markdown-compatible anchor slugs and handles duplicates.

        Args:
            document: Google Docs document dict from API

        Returns:
            Dict mapping slug to heading metadata:
            {
                'timeline--rollout-strategy': {
                    'text': 'Timeline & Rollout Strategy',
                    'level': 2,
                    'heading_id': 'h.abc123',
                    'index': 1547
                }
            }
        """
        heading_map = {}
        seen_slugs = {}
        content = document.get('body', {}).get('content', [])

        # Heading style name to level mapping
        heading_levels = {
            'HEADING_1': 1,
            'HEADING_2': 2,
            'HEADING_3': 3,
            'HEADING_4': 4,
            'HEADING_5': 5,
            'HEADING_6': 6,
        }

        for element in content:
            if 'paragraph' not in element:
                continue

            paragraph = element['paragraph']
            para_style = paragraph.get('paragraphStyle', {})
            named_style = para_style.get('namedStyleType')

            # Skip non-headings
            if named_style not in heading_levels:
                continue

            # Extract heading ID (format: h.xxxxx)
            heading_id = para_style.get('headingId')
            if not heading_id:
                logger.warning(f"Heading without headingId found: {named_style}")
                continue

            # Extract heading text from elements
            heading_text = ''
            start_index = None

            for text_elem in paragraph.get('elements', []):
                if 'textRun' in text_elem:
                    heading_text += text_elem['textRun'].get('content', '')
                    if start_index is None:
                        start_index = text_elem.get('startIndex', 0)

            # Clean up text (remove trailing newlines)
            heading_text = heading_text.strip()

            if not heading_text:
                continue

            # Generate unique slug
            base_slug = slugify_heading(heading_text)
            if not base_slug:
                logger.warning(f"Empty slug generated for heading: {heading_text}")
                continue

            unique_slug = get_unique_slug(base_slug, seen_slugs)

            # Store heading metadata
            heading_map[unique_slug] = {
                'text': heading_text,
                'level': heading_levels[named_style],
                'heading_id': heading_id,
                'index': start_index or 0
            }

        logger.info(f"Parsed {len(heading_map)} headings from document")
        return heading_map

    @staticmethod
    def _find_anchor_links(document: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Find all internal anchor links in document.

        Only processes links where the ENTIRE URL is #anchor-slug.
        External URLs (containing ://) are ignored.

        Args:
            document: Google Docs document dict from API

        Returns:
            List of anchor link dicts:
            [{
                'anchor': 'timeline--rollout-strategy',
                'start_index': 14,
                'end_index': 41,
                'text': 'Timeline & Rollout Strategy'
            }]
        """
        anchor_links = []
        content = document.get('body', {}).get('content', [])

        for element in content:
            if 'paragraph' not in element:
                continue

            paragraph = element['paragraph']

            for text_elem in paragraph.get('elements', []):
                if 'textRun' not in text_elem:
                    continue

                text_run = text_elem['textRun']
                text_style = text_run.get('textStyle', {})
                link_data = text_style.get('link')

                if not link_data:
                    continue

                url = link_data.get('url', '')

                # Only process internal anchor links (#slug)
                # Skip external URLs (containing ://)
                if not url.startswith('#') or '://' in url:
                    continue

                # Extract anchor slug (remove # prefix)
                anchor_slug = url[1:]  # Remove leading #

                anchor_links.append({
                    'anchor': anchor_slug,
                    'start_index': text_elem.get('startIndex', 0),
                    'end_index': text_elem.get('endIndex', 0),
                    'text': text_run.get('content', '').strip()
                })

        logger.info(f"Found {len(anchor_links)} anchor links in document")
        return anchor_links

    def convert_anchor_links(
        self,
        doc_id: str,
        heading_map: Dict[str, Dict[str, Any]],
        anchor_links: List[Dict[str, Any]]
    ) -> int:
        """
        Convert anchor links to headingId links.

        Replaces #anchor-slug URLs with Google Docs headingId links.
        Processes links in reverse index order to prevent index invalidation.

        Args:
            doc_id: Google Docs document ID
            heading_map: Map of slugs to heading metadata (from _parse_headings)
            anchor_links: List of anchor links (from _find_anchor_links)

        Returns:
            Number of links successfully converted

        Raises:
            GoogleDocsError: If batchUpdate fails
        """
        if not anchor_links:
            logger.info("No anchor links to convert")
            return 0

        # Build batchUpdate requests (process in reverse order)
        requests = []
        converted_count = 0

        # Sort by start_index descending (highest index first)
        sorted_links = sorted(anchor_links, key=lambda x: x['start_index'], reverse=True)

        for link in sorted_links:
            anchor = link['anchor']

            # Look up heading in map
            if anchor not in heading_map:
                logger.warning(f"⚠️  Anchor link #{anchor} not found in document headings")
                continue

            heading_id = heading_map[anchor]['heading_id']

            # Build updateTextStyle request
            requests.append({
                'updateTextStyle': {
                    'range': {
                        'startIndex': link['start_index'],
                        'endIndex': link['end_index']
                    },
                    'textStyle': {
                        'link': {'headingId': heading_id}
                    },
                    'fields': 'link'
                }
            })
            converted_count += 1

        if not requests:
            logger.info("No valid anchor links to convert")
            return 0

        # Execute batchUpdate
        try:
            self.docs_service.documents().batchUpdate(
                documentId=doc_id,
                body={'requests': requests}
            ).execute()

            logger.info(f"✅ Converted {converted_count} anchor links to headingId links")
            return converted_count

        except HttpError as error:
            logger.error(f"Failed to convert anchor links: {error}")
            raise GoogleDocsError(f"Failed to convert anchor links: {error}")

    def process_anchor_links(self, doc_id: str) -> int:
        """
        Complete workflow: discover headings, find anchor links, convert them.

        This is the main entry point for anchor link conversion.
        Call this after document upload/update and image embedding.

        Args:
            doc_id: Google Docs document ID

        Returns:
            Number of links successfully converted

        Raises:
            GoogleDocsError: If any step fails
        """
        try:
            # Step 1: Get document structure
            logger.info("🔗 Processing anchor links...")
            document = self.docs_service.documents().get(documentId=doc_id).execute()

            # Step 2: Parse headings
            heading_map = self._parse_headings(document)
            if not heading_map:
                logger.info("No headings found - skipping anchor link conversion")
                return 0

            # Step 3: Find anchor links
            anchor_links = self._find_anchor_links(document)
            if not anchor_links:
                logger.info("No anchor links found - skipping conversion")
                return 0

            # Step 4: Convert links
            converted_count = self.convert_anchor_links(doc_id, heading_map, anchor_links)
            return converted_count

        except HttpError as error:
            logger.error(f"Failed to process anchor links: {error}")
            raise GoogleDocsError(f"Failed to process anchor links: {error}")
