#!/bin/bash
#
# Git post-commit hook example for MD-to-Drive
# Place this in .git/hooks/post-commit and make it executable
#
# Usage:
#   cp examples/git-hook.sh .git/hooks/post-commit
#   chmod +x .git/hooks/post-commit

# Check if any markdown or CSV files were changed in the last commit
CHANGED_DOCS=$(git diff-tree --no-commit-id --name-only -r HEAD | grep -E '\.(md|csv)$')

if [ -n "$CHANGED_DOCS" ]; then
    echo ""
    echo "Documentation files changed:"
    echo "$CHANGED_DOCS"
    echo ""

    # Option 1: Auto-sync without prompt
    # echo "Auto-syncing to Google Drive..."
    # md-to-drive sync docs/ --quiet

    # Option 2: Ask before syncing
    read -p "Sync to Google Drive? (y/n) " -n 1 -r
    echo ""

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Syncing to Google Drive..."
        md-to-drive sync docs/
    else
        echo "Skipped sync. Run manually: md-to-drive sync docs/"
    fi
fi
