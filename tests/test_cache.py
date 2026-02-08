"""
Tests for sync cache functionality.

Tests file hashing, cache storage, and sync decision logic.
"""

import glob
import json
import logging
import os
from unittest.mock import patch

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


class TestAtomicSave:
    """Test atomic write behavior for save()."""

    def test_save_writes_to_temp_then_renames(self, tmp_path):
        """Verify save() writes to a temp file, then renames atomically."""
        cache_file = tmp_path / "cache" / ".test_cache.json"
        cache = SyncCache(cache_file=str(cache_file))
        cache.cache = {"key": {"hash": "abc123", "drive_id": "d1"}}

        with patch("src.drive_sync.cache.os.replace") as mock_replace:
            # os.replace is mocked, so the final file won't actually be
            # created by rename. We need to allow the temp write to happen
            # but intercept the rename.
            cache.save()

            # os.replace should have been called once
            assert mock_replace.call_count == 1
            args = mock_replace.call_args[0]
            temp_path_used = args[0]
            target_path_used = args[1]

            # Target should be the cache file
            assert target_path_used == str(cache_file)

            # Temp file should be in the same directory as cache file
            assert os.path.dirname(temp_path_used) == str(cache_file.parent)

    def test_save_temp_in_same_directory(self, tmp_path):
        """Verify temp file is created in the same directory as cache file."""
        cache_file = tmp_path / "cache" / ".test_cache.json"
        cache = SyncCache(cache_file=str(cache_file))
        cache.cache = {"key": {"hash": "abc123", "drive_id": "d1"}}

        with patch("src.drive_sync.cache.os.replace") as mock_replace:
            cache.save()

            args = mock_replace.call_args[0]
            temp_path_used = args[0]

            # Temp file must be in the same directory (same filesystem for
            # atomic rename on Docker volume mounts)
            assert os.path.dirname(temp_path_used) == str(cache_file.parent)

    def test_save_flushes_and_fsyncs_before_rename(self, tmp_path):
        """Verify flush() and fsync() are called before rename."""
        cache_file = tmp_path / "cache" / ".test_cache.json"
        cache = SyncCache(cache_file=str(cache_file))
        cache.cache = {"key": {"hash": "abc123", "drive_id": "d1"}}

        call_order = []
        original_open = open

        def recording_open(*args, **kwargs):
            fobj = original_open(*args, **kwargs)
            # Only wrap the temp file write, not other opens
            if len(args) > 1 and "w" in str(args[1]):
                original_flush = fobj.flush

                def tracked_flush():
                    call_order.append("flush")
                    return original_flush()

                fobj.flush = tracked_flush
            return fobj

        def patched_replace(src, dst):
            call_order.append("replace")
            os.rename(src, dst)

        def patched_fsync(fd):
            call_order.append("fsync")

        with (
            patch("builtins.open", side_effect=recording_open),
            patch("src.drive_sync.cache.os.replace", side_effect=patched_replace),
            patch("src.drive_sync.cache.os.fsync", side_effect=patched_fsync),
        ):
            cache.save()

        # flush and fsync must come before replace
        assert "flush" in call_order
        assert "fsync" in call_order
        assert "replace" in call_order
        assert call_order.index("flush") < call_order.index("replace")
        assert call_order.index("fsync") < call_order.index("replace")

    def test_save_cleans_temp_on_write_error(self, tmp_path):
        """If writing to the temp file fails, no orphaned temp file remains."""
        cache_file = tmp_path / "cache" / ".test_cache.json"
        cache = SyncCache(cache_file=str(cache_file))
        cache.cache = {"key": {"hash": "abc123", "drive_id": "d1"}}

        # Make json.dump raise an error to simulate write failure
        with patch("src.drive_sync.cache.json.dump", side_effect=OSError("disk full")):
            cache.save()

        # No .tmp files should remain in the cache directory
        cache_dir = str(cache_file.parent)
        if os.path.exists(cache_dir):
            tmp_files = glob.glob(os.path.join(cache_dir, "*.tmp"))
            assert len(tmp_files) == 0, f"Orphaned temp files found: {tmp_files}"

    def test_save_preserves_original_on_rename_error(self, tmp_path):
        """If rename fails, the original cache file is not corrupted."""
        cache_file = tmp_path / "cache" / ".test_cache.json"

        # Create an initial cache file with known content
        os.makedirs(str(cache_file.parent), exist_ok=True)
        original_data = {"original": {"hash": "orig_hash", "drive_id": "orig_id"}}
        with open(str(cache_file), "w") as f:
            json.dump(original_data, f)

        cache = SyncCache(cache_file=str(cache_file))
        cache.cache = {"new_key": {"hash": "new_hash", "drive_id": "new_id"}}

        # Make os.replace fail
        with patch(
            "src.drive_sync.cache.os.replace", side_effect=OSError("rename failed")
        ):
            cache.save()

        # Original file should be intact
        with open(str(cache_file)) as f:
            data = json.load(f)
        assert data == original_data

    def test_save_round_trip_with_atomic(self, tmp_path):
        """Verify save/load round-trip works correctly with atomic writes."""
        cache_file = tmp_path / "cache" / ".test_cache.json"

        cache1 = SyncCache(cache_file=str(cache_file))
        cache1.cache = {
            "/path/to/file.md": {
                "hash": "abc123",
                "drive_id": "xyz789",
                "last_sync": "2026-01-01T00:00:00",
            }
        }
        cache1.save()

        cache2 = SyncCache(cache_file=str(cache_file))
        loaded = cache2.load()

        assert "/path/to/file.md" in loaded
        assert loaded["/path/to/file.md"]["hash"] == "abc123"
        assert loaded["/path/to/file.md"]["drive_id"] == "xyz789"

    def test_save_creates_directory_with_atomic(self, tmp_path):
        """Verify directory creation still works with atomic write."""
        cache_file = tmp_path / "new_nested" / "dir" / "cache.json"

        cache = SyncCache(cache_file=str(cache_file))
        cache.cache = {"test": {"data": "value"}}
        cache.save()

        assert cache_file.exists()
        with open(str(cache_file)) as f:
            data = json.load(f)
        assert data == {"test": {"data": "value"}}

    def test_save_cleans_stale_tmp_files(self, tmp_path):
        """Stale .tmp files from previous crashes are cleaned up before writing."""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir(parents=True)
        cache_file = cache_dir / ".test_cache.json"

        # Create a stale .tmp file (simulating a previous crash)
        stale_tmp = cache_dir / ".test_cache.json.tmp"
        stale_tmp.write_text("stale data from a crash")

        cache = SyncCache(cache_file=str(cache_file))
        cache.cache = {"fresh": {"hash": "fresh_hash", "drive_id": "d1"}}
        cache.save()

        # Stale .tmp file should be gone
        assert not stale_tmp.exists()

        # New cache should be saved correctly
        assert cache_file.exists()
        with open(str(cache_file)) as f:
            data = json.load(f)
        assert data == {"fresh": {"hash": "fresh_hash", "drive_id": "d1"}}


class TestBackupOnLoad:
    """Test backup creation on save and fallback on load (Phase 2)."""

    def test_save_creates_backup(self, tmp_path):
        """AC-2.1: save() creates .bak copy after successful atomic write.

        Save twice with different data. After the second save, the .bak file
        should contain the first save's data (i.e., the backup is a copy of
        the cache file state BEFORE the current save).
        """
        cache_file = tmp_path / "cache" / ".test_cache.json"
        backup_file = str(cache_file) + ".bak"

        cache = SyncCache(cache_file=str(cache_file))

        # First save — writes data, creates .bak of the (previously existing)
        # cache file.  On first-ever save no prior file exists so .bak may or
        # may not be created.
        first_data = {"file1": {"hash": "h1", "drive_id": "d1"}}
        cache.cache = first_data.copy()
        cache.save()

        # Second save — the old cache file (first_data) should be backed up
        second_data = {"file2": {"hash": "h2", "drive_id": "d2"}}
        cache.cache = second_data.copy()
        cache.save()

        # .bak should exist and contain the first save's data
        assert os.path.exists(backup_file)
        with open(backup_file) as f:
            bak_data = json.load(f)
        assert bak_data == first_data

    def test_save_no_error_without_existing_file(self, tmp_path):
        """AC-2.2: First-ever save with no prior cache file succeeds without error."""
        cache_file = tmp_path / "cache" / ".test_cache.json"

        cache = SyncCache(cache_file=str(cache_file))
        cache.cache = {"key": {"hash": "h1", "drive_id": "d1"}}

        # Should not raise
        cache.save()

        # Cache file created successfully
        assert os.path.exists(str(cache_file))

    def test_load_fallback_on_corrupt_main(self, tmp_path):
        """AC-2.2 (load): load() returns backup data when main file is corrupt."""
        cache_file = tmp_path / ".test_cache.json"
        backup_file = str(cache_file) + ".bak"

        # Write valid data to backup
        backup_data = {"backed_up": {"hash": "bh", "drive_id": "bd"}}
        with open(backup_file, "w") as f:
            json.dump(backup_data, f)

        # Write corrupt JSON to main file
        with open(str(cache_file), "w") as f:
            f.write("not valid json {{{")

        cache = SyncCache(cache_file=str(cache_file))
        loaded = cache.load()

        assert loaded == backup_data

    def test_load_fallback_on_missing_main(self, tmp_path):
        """AC-2.3: load() returns backup data when main file is missing."""
        cache_file = tmp_path / ".test_cache.json"
        backup_file = str(cache_file) + ".bak"

        # Only backup exists, no main file
        backup_data = {"backed_up": {"hash": "bh", "drive_id": "bd"}}
        with open(backup_file, "w") as f:
            json.dump(backup_data, f)

        cache = SyncCache(cache_file=str(cache_file))
        loaded = cache.load()

        assert loaded == backup_data

    def test_load_empty_when_both_missing(self, tmp_path):
        """AC-2.4 (partial): load() returns {} when both main and backup missing."""
        cache_file = tmp_path / ".test_cache.json"

        cache = SyncCache(cache_file=str(cache_file))
        loaded = cache.load()

        assert loaded == {}

    def test_load_empty_when_both_corrupt(self, tmp_path):
        """AC-2.4: load() returns {} when both main and backup are corrupt."""
        cache_file = tmp_path / ".test_cache.json"
        backup_file = str(cache_file) + ".bak"

        with open(str(cache_file), "w") as f:
            f.write("corrupt main {{{")

        with open(backup_file, "w") as f:
            f.write("corrupt backup {{{")

        cache = SyncCache(cache_file=str(cache_file))
        loaded = cache.load()

        assert loaded == {}

    def test_load_logs_warning_on_fallback(self, tmp_path, caplog):
        """AC-2.5: WARNING logged when falling back to backup."""
        cache_file = tmp_path / ".test_cache.json"
        backup_file = str(cache_file) + ".bak"

        # Corrupt main, valid backup
        with open(str(cache_file), "w") as f:
            f.write("corrupt {{{")

        backup_data = {"backed_up": {"hash": "bh", "drive_id": "bd"}}
        with open(backup_file, "w") as f:
            json.dump(backup_data, f)

        cache = SyncCache(cache_file=str(cache_file))
        with caplog.at_level(logging.WARNING, logger="src.drive_sync.cache"):
            cache.load()

        # Should contain a warning about falling back to backup
        warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any("backup" in msg.lower() or "fallback" in msg.lower() or ".bak" in msg
                    for msg in warning_messages), (
            f"Expected warning about backup fallback, got: {warning_messages}"
        )

    def test_backup_failure_does_not_prevent_save(self, tmp_path):
        """AC-2.6: Backup creation failure doesn't prevent save from succeeding."""
        cache_file = tmp_path / "cache" / ".test_cache.json"

        cache = SyncCache(cache_file=str(cache_file))

        # First save to create the file
        cache.cache = {"first": {"hash": "h1", "drive_id": "d1"}}
        cache.save()

        # Now patch shutil.copy2 to fail during the second save
        new_data = {"second": {"hash": "h2", "drive_id": "d2"}}
        cache.cache = new_data.copy()

        with patch("src.drive_sync.cache.shutil.copy2", side_effect=OSError("permission denied")):
            cache.save()

        # Main cache file should still be updated with new data
        with open(str(cache_file)) as f:
            data = json.load(f)
        assert data == new_data

    def test_backup_preserves_metadata(self, tmp_path):
        """AC-2.8: .bak file is created via shutil.copy2 which preserves metadata."""
        cache_file = tmp_path / "cache" / ".test_cache.json"
        backup_file = str(cache_file) + ".bak"

        cache = SyncCache(cache_file=str(cache_file))
        cache.cache = {"v1": {"hash": "h1", "drive_id": "d1"}}
        cache.save()

        # Get mtime of the cache file after first save
        first_mtime = os.path.getmtime(str(cache_file))

        # Save again — this triggers backup of the existing file
        cache.cache = {"v2": {"hash": "h2", "drive_id": "d2"}}

        # Ensure some time passes so mtime would differ if copy2 doesn't preserve
        import time
        time.sleep(0.05)

        cache.save()

        # Backup should exist and its mtime should match the first save's file mtime
        # (copy2 preserves modification time)
        assert os.path.exists(backup_file)
        bak_mtime = os.path.getmtime(backup_file)
        assert abs(bak_mtime - first_mtime) < 1.0, (
            f"Backup mtime {bak_mtime} should be close to original {first_mtime}"
        )

    def test_is_empty_true_when_no_data_no_files(self, tmp_path):
        """AC-2.7: is_empty() returns True when cache empty AND no files on disk."""
        cache_file = tmp_path / ".test_cache.json"

        cache = SyncCache(cache_file=str(cache_file))
        cache.cache = {}

        # No files on disk, empty in-memory cache
        assert cache.is_empty() is True

    def test_is_empty_false_when_data_in_memory(self, tmp_path):
        """AC-2.7: is_empty() returns False when cache has data in memory."""
        cache_file = tmp_path / ".test_cache.json"

        cache = SyncCache(cache_file=str(cache_file))
        cache.cache = {"file": {"hash": "h1", "drive_id": "d1"}}

        assert cache.is_empty() is False

    def test_is_empty_false_when_main_file_exists(self, tmp_path):
        """AC-2.7: is_empty() returns False when main cache file exists on disk."""
        cache_file = tmp_path / ".test_cache.json"
        cache_file.write_text("{}")

        cache = SyncCache(cache_file=str(cache_file))
        cache.cache = {}

        assert cache.is_empty() is False

    def test_is_empty_false_when_backup_exists(self, tmp_path):
        """AC-2.7: is_empty() returns False when .bak file exists on disk."""
        cache_file = tmp_path / ".test_cache.json"
        backup_file = str(cache_file) + ".bak"

        # Only backup exists
        with open(backup_file, "w") as f:
            json.dump({"data": {}}, f)

        cache = SyncCache(cache_file=str(cache_file))
        cache.cache = {}

        assert cache.is_empty() is False


class TestRebuildFromDrive:
    """Test cache rebuild from Google Drive file listing (Phase 3)."""

    def test_rebuild_creates_entries_for_matched_files(self, tmp_path):
        """AC-3.4/3.5: rebuild creates cache entries for matched Drive-to-local files."""
        cache_file = tmp_path / ".test_cache.json"
        cache = SyncCache(cache_file=str(cache_file))
        cache.cache = {}

        # Create local files
        local_root = tmp_path / "project"
        local_root.mkdir()
        (local_root / "doc.md").write_text("Hello world")
        (local_root / "notes.txt").write_text("Some notes")

        drive_files = [
            {"id": "drive-1", "name": "doc.md"},
            {"id": "drive-2", "name": "notes.txt"},
        ]

        count = cache.rebuild_from_drive(drive_files, local_root)

        assert count == 2
        # Cache should have entries keyed by local file path strings
        assert len(cache.cache) == 2

    def test_rebuild_entries_have_verified_false(self, tmp_path):
        """AC-3.7: rebuilt entries have verified=False."""
        cache_file = tmp_path / ".test_cache.json"
        cache = SyncCache(cache_file=str(cache_file))
        cache.cache = {}

        local_root = tmp_path / "project"
        local_root.mkdir()
        (local_root / "doc.md").write_text("Content")

        drive_files = [{"id": "drive-1", "name": "doc.md"}]

        cache.rebuild_from_drive(drive_files, local_root)

        # Find the entry (keyed by local path string)
        entries = list(cache.cache.values())
        assert len(entries) == 1
        assert entries[0].get("verified") is False

    def test_rebuild_entries_have_correct_hash(self, tmp_path):
        """AC-3.7 (hash): rebuilt entries have hash matching local file."""
        cache_file = tmp_path / ".test_cache.json"
        cache = SyncCache(cache_file=str(cache_file))
        cache.cache = {}

        local_root = tmp_path / "project"
        local_root.mkdir()
        local_file = local_root / "doc.md"
        local_file.write_text("Hello world")

        expected_hash = SyncCache.get_file_hash(local_file)

        drive_files = [{"id": "drive-1", "name": "doc.md"}]
        cache.rebuild_from_drive(drive_files, local_root)

        entries = list(cache.cache.values())
        assert entries[0]["hash"] == expected_hash

    def test_rebuild_entries_have_drive_id(self, tmp_path):
        """Rebuilt entries include the correct drive_id."""
        cache_file = tmp_path / ".test_cache.json"
        cache = SyncCache(cache_file=str(cache_file))
        cache.cache = {}

        local_root = tmp_path / "project"
        local_root.mkdir()
        (local_root / "doc.md").write_text("Content")

        drive_files = [{"id": "drive-abc-123", "name": "doc.md"}]
        cache.rebuild_from_drive(drive_files, local_root)

        entries = list(cache.cache.values())
        assert entries[0]["drive_id"] == "drive-abc-123"

    def test_rebuild_skips_no_local_match(self, tmp_path):
        """AC-3.6: Drive files without a local match are skipped."""
        cache_file = tmp_path / ".test_cache.json"
        cache = SyncCache(cache_file=str(cache_file))
        cache.cache = {}

        local_root = tmp_path / "project"
        local_root.mkdir()
        (local_root / "doc.md").write_text("Content")

        drive_files = [
            {"id": "drive-1", "name": "doc.md"},
            {"id": "drive-2", "name": "nonexistent.txt"},  # No local match
        ]

        count = cache.rebuild_from_drive(drive_files, local_root)

        assert count == 1
        assert len(cache.cache) == 1

    def test_rebuild_skips_ambiguous_matches(self, tmp_path):
        """AC-3.5: Files with same name in multiple dirs are skipped."""
        cache_file = tmp_path / ".test_cache.json"
        cache = SyncCache(cache_file=str(cache_file))
        cache.cache = {}

        local_root = tmp_path / "project"
        local_root.mkdir()
        # Same filename in two subdirectories
        sub1 = local_root / "sub1"
        sub1.mkdir()
        (sub1 / "readme.md").write_text("Sub1 readme")

        sub2 = local_root / "sub2"
        sub2.mkdir()
        (sub2 / "readme.md").write_text("Sub2 readme")

        drive_files = [{"id": "drive-1", "name": "readme.md"}]

        count = cache.rebuild_from_drive(drive_files, local_root)

        assert count == 0
        assert len(cache.cache) == 0

    def test_rebuild_returns_count(self, tmp_path):
        """AC-3.10: rebuild returns count of rebuilt entries."""
        cache_file = tmp_path / ".test_cache.json"
        cache = SyncCache(cache_file=str(cache_file))
        cache.cache = {}

        local_root = tmp_path / "project"
        local_root.mkdir()
        (local_root / "a.md").write_text("A")
        (local_root / "b.md").write_text("B")
        (local_root / "c.md").write_text("C")

        drive_files = [
            {"id": "d1", "name": "a.md"},
            {"id": "d2", "name": "b.md"},
            {"id": "d3", "name": "c.md"},
            {"id": "d4", "name": "missing.md"},  # No local match
        ]

        count = cache.rebuild_from_drive(drive_files, local_root)

        assert count == 3

    def test_rebuild_calls_save(self, tmp_path):
        """AC-3.8: rebuild calls save() after building entries."""
        cache_file = tmp_path / ".test_cache.json"
        cache = SyncCache(cache_file=str(cache_file))
        cache.cache = {}

        local_root = tmp_path / "project"
        local_root.mkdir()
        (local_root / "doc.md").write_text("Content")

        drive_files = [{"id": "d1", "name": "doc.md"}]

        with patch.object(cache, "save") as mock_save:
            cache.rebuild_from_drive(drive_files, local_root)
            mock_save.assert_called_once()

    def test_rebuild_with_empty_drive_files(self, tmp_path):
        """Rebuild with empty Drive file list returns 0."""
        cache_file = tmp_path / ".test_cache.json"
        cache = SyncCache(cache_file=str(cache_file))
        cache.cache = {}

        local_root = tmp_path / "project"
        local_root.mkdir()
        (local_root / "doc.md").write_text("Content")

        count = cache.rebuild_from_drive([], local_root)

        assert count == 0
        assert len(cache.cache) == 0

    def test_rebuild_with_empty_local_directory(self, tmp_path):
        """Rebuild with no local files returns 0."""
        cache_file = tmp_path / ".test_cache.json"
        cache = SyncCache(cache_file=str(cache_file))
        cache.cache = {}

        local_root = tmp_path / "project"
        local_root.mkdir()

        drive_files = [{"id": "d1", "name": "doc.md"}]

        count = cache.rebuild_from_drive(drive_files, local_root)

        assert count == 0
        assert len(cache.cache) == 0

    def test_rebuild_uses_str_path_as_cache_key(self, tmp_path):
        """Cache keys use str(local_path) consistent with update() method."""
        cache_file = tmp_path / ".test_cache.json"
        cache = SyncCache(cache_file=str(cache_file))
        cache.cache = {}

        local_root = tmp_path / "project"
        local_root.mkdir()
        local_file = local_root / "doc.md"
        local_file.write_text("Content")

        drive_files = [{"id": "d1", "name": "doc.md"}]
        cache.rebuild_from_drive(drive_files, local_root)

        assert str(local_file) in cache.cache

    def test_rebuild_entries_have_last_sync(self, tmp_path):
        """Rebuilt entries include a last_sync timestamp."""
        cache_file = tmp_path / ".test_cache.json"
        cache = SyncCache(cache_file=str(cache_file))
        cache.cache = {}

        local_root = tmp_path / "project"
        local_root.mkdir()
        (local_root / "doc.md").write_text("Content")

        drive_files = [{"id": "d1", "name": "doc.md"}]
        cache.rebuild_from_drive(drive_files, local_root)

        entries = list(cache.cache.values())
        assert "last_sync" in entries[0]

    def test_should_sync_works_with_rebuilt_entries(self, tmp_path):
        """AC-3.9: should_sync() treats rebuilt entries same as normal entries."""
        cache_file = tmp_path / ".test_cache.json"
        cache = SyncCache(cache_file=str(cache_file))
        cache.cache = {}

        local_root = tmp_path / "project"
        local_root.mkdir()
        local_file = local_root / "doc.md"
        local_file.write_text("Original content")

        drive_files = [{"id": "d1", "name": "doc.md"}]
        cache.rebuild_from_drive(drive_files, local_root)

        # File unchanged since rebuild — should NOT sync
        should_sync, reason = cache.should_sync(local_file)
        assert should_sync is False
        assert reason == "already synced"

        # Modify the file — should sync
        local_file.write_text("Modified content")
        should_sync, reason = cache.should_sync(local_file)
        assert should_sync is True
        assert reason == "file modified"
