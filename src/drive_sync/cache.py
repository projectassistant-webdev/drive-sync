"""
Caching system for Drive Sync.

Tracks file hashes to avoid re-syncing unchanged files.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class SyncCache:
    """Manages sync cache for tracking file changes.

    Tracks MD5 hashes of local files and their corresponding Google Drive
    file IDs to avoid re-syncing unchanged files.
    """

    def __init__(self, cache_file: str | None = None, folder_id: str | None = None):
        """
        Initialize sync cache

        Args:
            cache_file: Path to cache file (optional - derived from folder_id if not provided)
            folder_id: Google Drive folder ID (used to create project-specific cache)
        """
        if cache_file:
            self.cache_file = cache_file
        elif folder_id:
            # Create project-specific cache file based on folder ID
            # Use first 12 chars of folder_id for readability
            safe_id = folder_id[:12] if len(folder_id) > 12 else folder_id
            self.cache_file = f'cache/.sync_cache_{safe_id}.json'
        else:
            # Fallback to default (legacy behavior)
            self.cache_file = 'cache/.sync_cache.json'

        self.folder_id = folder_id
        self.cache: dict[str, dict] = {}

    def load(self) -> dict[str, dict]:
        """
        Load cache from disk

        Returns:
            Cache dictionary
        """
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file) as f:
                    self.cache = json.load(f)
                    logger.info(f"Loaded cache with {len(self.cache)} entries")
            except Exception as e:
                logger.warning(f"Error loading cache: {e}")
                self.cache = {}
        else:
            self.cache = {}
            logger.info("No existing cache found - starting fresh")

        return self.cache

    def save(self) -> None:
        """Save cache to disk."""
        try:
            # Ensure cache directory exists
            cache_dir = os.path.dirname(self.cache_file)
            if cache_dir and not os.path.exists(cache_dir):
                logger.info(f"Creating cache directory: {cache_dir}")
                os.makedirs(cache_dir, exist_ok=True)

            logger.debug(f"Saving cache to: {self.cache_file}")
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f, indent=2)

            logger.info(f"Cache saved successfully ({len(self.cache)} entries)")
        except Exception as e:
            logger.error(f"Error saving cache: {e}")

    @staticmethod
    def get_file_hash(file_path: Path) -> str | None:
        """
        Get MD5 hash of file content

        Args:
            file_path: Path to file

        Returns:
            MD5 hash string or None if error
        """
        hash_md5 = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception as e:
            logger.warning(f"Error hashing {file_path}: {e}")
            return None

    def should_sync(self, file_path: Path) -> tuple[bool, str]:
        """
        Check if file should be synced based on cache

        Args:
            file_path: Path to file

        Returns:
            Tuple of (should_sync: bool, reason: str)
        """
        file_hash = self.get_file_hash(file_path)
        if not file_hash:
            return True, "error reading file"

        cache_key = str(file_path)

        # File not in cache - needs sync
        if cache_key not in self.cache:
            return True, "new file"

        cached_data = self.cache[cache_key]

        # Hash changed - needs sync
        if cached_data.get('hash') != file_hash:
            return True, "file modified"

        # Already synced and unchanged
        return False, "already synced"

    def update(self, file_path: Path, drive_file_id: str) -> None:
        """Update cache with synced file info.

        Args:
            file_path: Local file path.
            drive_file_id: Google Drive file ID.
        """
        file_hash = self.get_file_hash(file_path)
        if file_hash:
            self.cache[str(file_path)] = {
                'hash': file_hash,
                'drive_id': drive_file_id,
                'last_sync': datetime.now().isoformat(),
            }

    def get_stats(self) -> dict[str, int]:
        """
        Get cache statistics

        Returns:
            Dictionary with cache stats
        """
        return {
            'total_entries': len(self.cache),
            'total_files': len(self.cache)
        }
