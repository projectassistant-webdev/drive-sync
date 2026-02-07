"""
Drive Sync - Enhanced with Mermaid diagram rendering.

Supports both local mermaid-cli and mermaid.ink API backends.
"""

from __future__ import annotations

__version__ = "2.1.0"

from .gdocs import GoogleDocsError, GoogleDocsService
from .gdrive import GoogleDriveError, GoogleDriveService
from .mermaid_api import MermaidAPIError, MermaidCLIError, render_mermaid_diagram
from .sync import GoogleDriveSync

__all__ = [
    "GoogleDocsError",
    "GoogleDocsService",
    "GoogleDriveError",
    "GoogleDriveService",
    "GoogleDriveSync",
    "MermaidAPIError",
    "MermaidCLIError",
    "render_mermaid_diagram",
]
