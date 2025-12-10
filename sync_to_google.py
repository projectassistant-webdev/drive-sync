#!/usr/bin/env python3
"""
Drive Sync - Entry point script.

Enhanced with zero-dependency Mermaid diagram rendering via mermaid.ink API.
"""

import os
import sys
import logging
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from drive_sync.sync import GoogleDriveSync


def setup_logging():
    """Configure logging output"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(message)s'
    )


def main():
    """Main sync workflow"""
    setup_logging()
    logger = logging.getLogger(__name__)

    logger.info("=" * 60)
    logger.info("📄 Drive Sync (with Mermaid support)")
    logger.info("=" * 60)
    logger.info("")

    # Configuration from environment
    folder_id = os.getenv('GOOGLE_DRIVE_FOLDER_ID')
    sync_paths = os.getenv('SYNC_PATHS', 'docs').split(',')
    rate_limit_delay = float(os.getenv('RATE_LIMIT_DELAY', '0.5'))
    batch_size = int(os.getenv('BATCH_SIZE', '10'))
    enable_mermaid = os.getenv('ENABLE_MERMAID', 'true').lower() == 'true'

    if not folder_id:
        logger.error("❌ GOOGLE_DRIVE_FOLDER_ID not set in environment")
        sys.exit(1)

    logger.info(f"📂 Target folder ID: {folder_id}")
    logger.info(f"📝 Paths to sync: {', '.join(sync_paths)}")
    logger.info(f"🎨 Mermaid diagrams: {'enabled' if enable_mermaid else 'disabled'}")
    logger.info("")

    try:
        # Initialize sync service
        sync = GoogleDriveSync(
            credentials_file='credentials.json',
            folder_id=folder_id,
            use_cache=True,
            rate_limit_delay=rate_limit_delay,
            batch_size=batch_size,
            enable_mermaid=enable_mermaid
        )

        # Sync each configured path
        for path_str in sync_paths:
            path = Path(path_str.strip())

            if not path.exists():
                logger.warning(f"⚠️  Path not found: {path}")
                continue

            logger.info(f"🔄 Syncing: {path}")

            if path.is_file():
                # Sync single file
                sync.sync_file(path, folder_id)
            elif path.is_dir():
                # Sync directory
                sync.sync_directory(path, recursive=True)

        # Finalize
        sync.finalize()

        logger.info("")
        logger.info("=" * 60)
        logger.info("✅ Sync complete!")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"\n❌ Sync failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
