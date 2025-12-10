"""
Drive Sync - Enhanced with Mermaid diagram rendering.

Zero dependencies approach using mermaid.ink API.
"""

__version__ = "2.0.0"

from .sync import GoogleDriveSync
from .mermaid_api import render_mermaid_diagram, MermaidAPIError
from .gdocs import GoogleDocsService, GoogleDocsError
from .gdrive import GoogleDriveService, GoogleDriveError

__all__ = [
    "GoogleDriveSync",
    "render_mermaid_diagram",
    "MermaidAPIError",
    "GoogleDocsService",
    "GoogleDocsError",
    "GoogleDriveService",
    "GoogleDriveError",
]
