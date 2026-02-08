"""
Caching system for Drive Sync.

Tracks file hashes to avoid re-syncing unchanged files.
"""

from __future__ import annotations

import contextlib
import glob
import hashlib
import json
import logging
import os
import shutil
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

    @property
    def backup_file(self) -> str:
        """Path to the backup cache file."""
        return self.cache_file + '.bak'

    def is_empty(self) -> bool:
        """Check if cache is completely empty (no data and no files on disk).

        Returns True only when the in-memory cache is empty AND neither the
        main cache file nor the .bak backup file exist on disk. This is used
        to detect total cache loss for rebuild triggers.
        """
        if self.cache:
            return False
        if os.path.exists(self.cache_file):
            return False
        return not os.path.exists(self.backup_file)

    def load(self) -> dict[str, dict]:
        """Load cache from disk.

        Attempts to load from the main cache file first. If the main file
        is missing or corrupt, falls back to the .bak backup file. If both
        are unavailable, starts with an empty cache.

        Returns:
            Cache dictionary
        """
        # Attempt to load from main cache file
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file) as f:
                    self.cache = json.load(f)
                    logger.info(f"Loaded cache with {len(self.cache)} entries")
                    return self.cache
            except Exception as e:
                logger.warning(f"Error loading cache: {e}")
                # Fall through to backup attempt

        # Main file missing or corrupt — attempt backup fallback
        if os.path.exists(self.backup_file):
            logger.warning(
                f"Falling back to backup cache file: {self.backup_file}"
            )
            try:
                with open(self.backup_file) as f:
                    self.cache = json.load(f)
                    logger.info(
                        f"Loaded cache from backup with {len(self.cache)} entries"
                    )
                    return self.cache
            except Exception as e:
                logger.warning(f"Error loading backup cache: {e}")

        # Both missing or corrupt — start fresh
        self.cache = {}
        logger.info("No existing cache found - starting fresh")
        return self.cache

    def save(self) -> None:
        """Save cache to disk using atomic write with backup.

        Creates a .bak backup of the existing cache file (if present) before
        overwriting, then writes to a temporary file in the same directory
        and atomically replaces the target file using os.replace(). This
        prevents cache corruption if the process crashes mid-write.
        """
        temp_path = None
        try:
            # Ensure cache directory exists
            cache_dir = os.path.dirname(self.cache_file)
            if cache_dir and not os.path.exists(cache_dir):
                logger.info(f"Creating cache directory: {cache_dir}")
                os.makedirs(cache_dir, exist_ok=True)

            # Backup existing cache file before overwriting (AC-2.1)
            if os.path.exists(self.cache_file):
                try:
                    shutil.copy2(self.cache_file, self.backup_file)
                    logger.debug(f"Backup created: {self.backup_file}")
                except OSError as e:
                    # Backup failure must not prevent save (AC-2.6)
                    logger.warning(f"Could not create backup: {e}")

            # Clean up stale .tmp files from previous crashes
            if cache_dir and os.path.exists(cache_dir):
                stale_pattern = os.path.join(cache_dir, "*.tmp")
                for stale_tmp in glob.glob(stale_pattern):
                    try:
                        os.remove(stale_tmp)
                        logger.debug(f"Cleaned up stale temp file: {stale_tmp}")
                    except OSError as e:
                        logger.warning(f"Could not remove stale temp file {stale_tmp}: {e}")

            # Determine temp file path in the same directory (same filesystem
            # required for atomic rename, especially on Docker volume mounts)
            temp_path = self.cache_file + '.tmp'

            logger.debug(f"Saving cache to: {self.cache_file}")

            # Write to temp file
            with open(temp_path, 'w') as f:
                json.dump(self.cache, f, indent=2)
                f.flush()
                os.fsync(f.fileno())

            # Atomically replace the target file
            os.replace(temp_path, self.cache_file)
            temp_path = None  # Rename succeeded, no cleanup needed

            logger.info(f"Cache saved successfully ({len(self.cache)} entries)")
        except Exception as e:
            logger.error(f"Error saving cache: {e}")
            # Clean up temp file on error
            if temp_path and os.path.exists(temp_path):
                with contextlib.suppress(OSError):
                    os.remove(temp_path)

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

    def rebuild_from_drive(self, drive_files: list[dict[str, str]], local_root: Path) -> int:
        """Rebuild cache from Google Drive file listing.

        Matches Drive filenames to local files under local_root.
        Rebuilt entries have verified=False since we cannot confirm
        content matches without a prior sync record.

        Args:
            drive_files: List of dicts with 'id' and 'name' from Drive.
            local_root: Root directory of local files to match against.

        Returns:
            Number of cache entries rebuilt.
        """
        if not drive_files:
            logger.debug("No Drive files provided for rebuild")
            self.save()
            return 0

        # Walk local_root to build filename -> [local_path, ...] map
        local_map: dict[str, list[Path]] = {}
        local_root = Path(local_root)
        if local_root.exists():
            for local_file in local_root.rglob('*'):
                if local_file.is_file():
                    name = local_file.name
                    if name not in local_map:
                        local_map[name] = []
                    local_map[name].append(local_file)

        rebuilt_count = 0
        for drive_file in drive_files:
            name = drive_file['name']
            drive_id = drive_file['id']

            local_matches = local_map.get(name, [])

            if len(local_matches) == 0:
                logger.debug(f"Rebuild skip (no local match): {name}")
                continue

            if len(local_matches) > 1:
                logger.warning(
                    f"Rebuild skip (ambiguous, {len(local_matches)} local matches): {name}"
                )
                continue

            # Exactly one match
            local_path = local_matches[0]
            file_hash = self.get_file_hash(local_path)
            if file_hash is None:
                logger.warning(f"Rebuild skip (hash error): {name}")
                continue

            cache_key = str(local_path)
            self.cache[cache_key] = {
                'hash': file_hash,
                'drive_id': drive_id,
                'last_sync': datetime.now().isoformat(),
                'verified': False,
            }
            rebuilt_count += 1
            logger.debug(f"Rebuilt cache entry: {name} -> {drive_id}")

        self.save()
        logger.info(f"Cache rebuilt with {rebuilt_count} entries from Drive listing")
        return rebuilt_count

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
