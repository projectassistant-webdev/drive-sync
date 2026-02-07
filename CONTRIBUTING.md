# Contributing to Drive Sync

Thanks for your interest in contributing!

## Reporting Bugs

Before creating bug reports, please check existing issues. When creating a bug report, include:

- Clear and descriptive title
- Steps to reproduce the problem
- Expected vs actual behavior
- Error messages and stack traces
- Python version and OS

## Suggesting Enhancements

Enhancement suggestions are tracked as GitHub issues. Please include:

- Clear and descriptive title
- Step-by-step description of the enhancement
- Why this enhancement would be useful

## Pull Requests

- Follow existing code style (enforced by ruff)
- Include tests for new features
- Ensure `pytest tests/` passes with 80%+ coverage
- Update documentation as needed

## Development Setup

```bash
# Clone the repo
git clone https://github.com/projectassistant-webdev/drive-sync.git
cd drive-sync

# Option 1: Docker (recommended)
docker compose build
docker compose run --rm drive-sync pytest tests/ -v

# Option 2: Local
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pytest tests/ -v
```

## Project Structure

```
drive-sync/
├── src/drive_sync/
│   ├── sync/              # Core sync logic (orchestrator, processors, uploaders)
│   ├── auth.py            # Google authentication
│   ├── cache.py           # Smart caching system
│   ├── converter.py       # Markdown/CSV conversion
│   ├── gdocs.py           # Google Docs API
│   ├── gdrive.py          # Google Drive API
│   ├── mermaid_api.py     # Mermaid diagram rendering
│   ├── ascii_renderer.py  # ASCII wireframe rendering
│   ├── code_renderer.py   # Code syntax highlighting
│   └── utils.py           # Shared utilities
├── tests/                 # Test suite (92% coverage)
├── examples/              # Example configurations
├── sync_to_google.py      # Entry point
└── pyproject.toml         # Project configuration
```

## Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add new feature
fix: fix a bug
docs: documentation changes
test: adding tests
chore: maintenance tasks
refactor: code restructuring
```

## Questions?

Feel free to open an issue with the `question` label.
