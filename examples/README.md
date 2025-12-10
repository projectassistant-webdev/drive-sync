# Examples

This directory contains example configuration files and integration examples for Drive Sync.

## Configuration Examples

### credentials.example.json
Template for Google Cloud service account credentials.

**Setup:**
1. Download your credentials from Google Cloud Console
2. Copy to project root as `credentials.json` (not this example file)
3. Never commit the real `credentials.json`

### .env.example
Environment variable template for configuration.

**Setup:**
1. Copy to `.env` in your project root
2. Update `GOOGLE_DRIVE_FOLDER_ID` with your folder ID
3. Customize `SYNC_PATHS` and `SYNC_SUBFOLDERS` as needed

### config.yml
Example YAML configuration file for more complex setups.

## Integration Examples

### git-hook.sh
Post-commit hook that automatically syncs docs on every commit.

**Setup:**
```bash
cp examples/git-hook.sh .git/hooks/post-commit
chmod +x .git/hooks/post-commit
```

### github-action.yml
GitHub Actions workflow for automated syncing in CI/CD.

**Setup:**
```bash
mkdir -p .github/workflows
cp examples/github-action.yml .github/workflows/sync-docs.yml
```

Remember to add `GOOGLE_DRIVE_CREDENTIALS` as a GitHub secret!

## Docker Example

Run sync with Docker Compose:

```bash
docker compose up
```
