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
