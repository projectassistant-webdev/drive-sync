"""
Tests for sync cache functionality.

Tests file hashing, cache storage, and sync decision logic.
"""

import pytest
import json
from pathlib import Path
from src.drive_sync.cache import SyncCache


class TestSyncCacheInitialization:
    """Test cache initialization and file path handling."""

    def test_default_cache_file(self):
        """Test default cache file path when no arguments provided."""
        cache = SyncCache()
        assert cache.cache_file == 'cache/.sync_cache.json'

    def test_custom_cache_file(self):
        """Test custom cache file path."""
        cache = SyncCache(cache_file='custom/path/.cache.json')
        assert cache.cache_file == 'custom/path/.cache.json'

    def test_folder_id_based_cache_file(self):
        """Test cache file derived from folder ID."""
        cache = SyncCache(folder_id='0AFmzltzwVhciUk9PVA')
        assert cache.cache_file == 'cache/.sync_cache_0AFmzltzwVhc.json'

    def test_short_folder_id(self):
        """Test cache file with short folder ID (less than 12 chars)."""
        cache = SyncCache(folder_id='abc123')
        assert cache.cache_file == 'cache/.sync_cache_abc123.json'

    def test_custom_cache_takes_precedence(self):
        """Test that explicit cache_file takes precedence over folder_id."""
        cache = SyncCache(cache_file='explicit.json', folder_id='should_be_ignored')
        assert cache.cache_file == 'explicit.json'


class TestFileHashing:
    """Test file hash computation."""

    def test_hash_simple_file(self, tmp_path):
        """Test hashing a simple text file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        file_hash = SyncCache.get_file_hash(test_file)

        assert file_hash is not None
        assert len(file_hash) == 32  # MD5 produces 32 hex chars
        # Known MD5 of "Hello, World!"
        assert file_hash == '65a8e27d8879283831b664bd8b7f0ad4'

    def test_hash_binary_file(self, tmp_path):
        """Test hashing a binary file."""
        test_file = tmp_path / "test.bin"
        test_file.write_bytes(bytes([0x00, 0x01, 0x02, 0xFF]))

        file_hash = SyncCache.get_file_hash(test_file)

        assert file_hash is not None
        assert len(file_hash) == 32

    def test_hash_large_file(self, tmp_path):
        """Test hashing a larger file (chunked reading)."""
        test_file = tmp_path / "large.txt"
        # Write more than 4096 bytes to test chunking
        test_file.write_text("X" * 10000)

        file_hash = SyncCache.get_file_hash(test_file)

        assert file_hash is not None
        assert len(file_hash) == 32

    def test_hash_nonexistent_file(self, tmp_path):
        """Test hashing a nonexistent file returns None."""
        nonexistent = tmp_path / "does_not_exist.txt"

        file_hash = SyncCache.get_file_hash(nonexistent)

        assert file_hash is None

    def test_same_content_same_hash(self, tmp_path):
        """Test that identical content produces identical hash."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        content = "Same content here"

        file1.write_text(content)
        file2.write_text(content)

        assert SyncCache.get_file_hash(file1) == SyncCache.get_file_hash(file2)

    def test_different_content_different_hash(self, tmp_path):
        """Test that different content produces different hash."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"

        file1.write_text("Content A")
        file2.write_text("Content B")

        assert SyncCache.get_file_hash(file1) != SyncCache.get_file_hash(file2)


class TestShouldSync:
    """Test sync decision logic."""

    def test_new_file_should_sync(self, tmp_path):
        """Test that new files (not in cache) should sync."""
        cache = SyncCache()
        cache.cache = {}  # Empty cache

        test_file = tmp_path / "new_file.md"
        test_file.write_text("New content")

        should_sync, reason = cache.should_sync(test_file)

        assert should_sync is True
        assert reason == "new file"

    def test_unchanged_file_should_not_sync(self, tmp_path):
        """Test that unchanged files should not sync."""
        test_file = tmp_path / "existing.md"
        test_file.write_text("Original content")

        cache = SyncCache()
        file_hash = SyncCache.get_file_hash(test_file)
        cache.cache = {
            str(test_file): {
                'hash': file_hash,
                'drive_id': 'abc123',
                'last_sync': '2025-01-01T00:00:00'
            }
        }

        should_sync, reason = cache.should_sync(test_file)

        assert should_sync is False
        assert reason == "already synced"

    def test_modified_file_should_sync(self, tmp_path):
        """Test that modified files should sync."""
        test_file = tmp_path / "modified.md"
        test_file.write_text("Original content")

        cache = SyncCache()
        # Cache has old hash
        cache.cache = {
            str(test_file): {
                'hash': 'old_hash_value_123456789012',
                'drive_id': 'abc123',
                'last_sync': '2025-01-01T00:00:00'
            }
        }

        should_sync, reason = cache.should_sync(test_file)

        assert should_sync is True
        assert reason == "file modified"


class TestCacheUpdate:
    """Test cache update functionality."""

    def test_update_adds_entry(self, tmp_path):
        """Test that update adds a cache entry."""
        test_file = tmp_path / "new.md"
        test_file.write_text("Content")

        cache = SyncCache()
        cache.cache = {}

        cache.update(test_file, 'drive_id_123')

        assert str(test_file) in cache.cache
        entry = cache.cache[str(test_file)]
        assert entry['drive_id'] == 'drive_id_123'
        assert 'hash' in entry
        assert 'last_sync' in entry

    def test_update_overwrites_entry(self, tmp_path):
        """Test that update overwrites existing entry."""
        test_file = tmp_path / "existing.md"
        test_file.write_text("Updated content")

        cache = SyncCache()
        cache.cache = {
            str(test_file): {
                'hash': 'old_hash',
                'drive_id': 'old_drive_id',
                'last_sync': '2024-01-01T00:00:00'
            }
        }

        cache.update(test_file, 'new_drive_id')

        entry = cache.cache[str(test_file)]
        assert entry['drive_id'] == 'new_drive_id'
        assert entry['hash'] != 'old_hash'


class TestCachePersistence:
    """Test cache save and load functionality."""

    def test_save_and_load(self, tmp_path):
        """Test saving and loading cache."""
        cache_file = tmp_path / "cache" / ".test_cache.json"

        # Create and save cache
        cache1 = SyncCache(cache_file=str(cache_file))
        cache1.cache = {
            '/path/to/file.md': {
                'hash': 'abc123',
                'drive_id': 'xyz789',
                'last_sync': '2025-01-01T00:00:00'
            }
        }
        cache1.save()

        # Load in new instance
        cache2 = SyncCache(cache_file=str(cache_file))
        loaded = cache2.load()

        assert '/path/to/file.md' in loaded
        assert loaded['/path/to/file.md']['hash'] == 'abc123'
        assert loaded['/path/to/file.md']['drive_id'] == 'xyz789'

    def test_load_nonexistent_cache(self, tmp_path):
        """Test loading when cache file doesn't exist."""
        cache_file = tmp_path / "nonexistent.json"

        cache = SyncCache(cache_file=str(cache_file))
        loaded = cache.load()

        assert loaded == {}

    def test_load_invalid_json(self, tmp_path):
        """Test loading corrupted cache file."""
        cache_file = tmp_path / "corrupt.json"
        cache_file.write_text("not valid json {{{")

        cache = SyncCache(cache_file=str(cache_file))
        loaded = cache.load()

        assert loaded == {}  # Should return empty on error

    def test_save_creates_directory(self, tmp_path):
        """Test that save creates cache directory if needed."""
        cache_file = tmp_path / "nested" / "dir" / "cache.json"

        cache = SyncCache(cache_file=str(cache_file))
        cache.cache = {'test': {'data': 'value'}}
        cache.save()

        assert cache_file.exists()
        with open(cache_file) as f:
            data = json.load(f)
        assert data == {'test': {'data': 'value'}}


class TestCacheStats:
    """Test cache statistics."""

    def test_empty_cache_stats(self):
        """Test stats for empty cache."""
        cache = SyncCache()
        cache.cache = {}

        stats = cache.get_stats()

        assert stats['total_entries'] == 0
        assert stats['total_files'] == 0

    def test_populated_cache_stats(self):
        """Test stats for populated cache."""
        cache = SyncCache()
        cache.cache = {
            '/file1.md': {'hash': 'a', 'drive_id': '1'},
            '/file2.md': {'hash': 'b', 'drive_id': '2'},
            '/file3.md': {'hash': 'c', 'drive_id': '3'},
        }

        stats = cache.get_stats()

        assert stats['total_entries'] == 3
        assert stats['total_files'] == 3
