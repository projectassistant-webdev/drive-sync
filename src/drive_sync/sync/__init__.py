"""
Sync package for Google Drive synchronization.

Re-exports ``GoogleDriveSync`` and related constants for backward
compatibility so that ``from drive_sync.sync import GoogleDriveSync``
continues to work after the module-to-package conversion.
"""

from __future__ import annotations

from .orchestrator import DEFAULT_BATCH_SIZE, DEFAULT_RATE_LIMIT_DELAY, GoogleDriveSync

__all__ = [
    "DEFAULT_BATCH_SIZE",
    "DEFAULT_RATE_LIMIT_DELAY",
    "GoogleDriveSync",
]
