"""
Drive Sync - Enhanced with Mermaid diagram rendering.

Supports both local mermaid-cli and mermaid.ink API backends.
"""

__version__ = "2.0.0"

from .sync import GoogleDriveSync
from .mermaid_api import render_mermaid_diagram, MermaidAPIError, MermaidCLIError
from .gdocs import GoogleDocsService, GoogleDocsError
from .gdrive import GoogleDriveService, GoogleDriveError

__all__ = [
    "GoogleDriveSync",
    "render_mermaid_diagram",
    "MermaidAPIError",
    "MermaidCLIError",
    "GoogleDocsService",
    "GoogleDocsError",
    "GoogleDriveService",
    "GoogleDriveError",
]
