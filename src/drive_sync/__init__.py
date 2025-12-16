"""
Drive Sync - Enhanced with Mermaid diagram rendering.

Supports multiple rendering backends:
- Local mermaid-cli (mmdc) - preferred for reliability
- mermaid.ink API - fallback when CLI unavailable
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
