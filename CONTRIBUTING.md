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

- Follow PEP 8 style guide
- Include tests for new features
- Update documentation as needed

## Development Setup

```bash
# Clone the repo
git clone https://github.com/projectassistant-webdev/drive-sync.git
cd drive-sync

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Project Structure

```
drive-sync/
├── src/drive_sync/       # Main package
│   ├── auth.py           # Google authentication
│   ├── cache.py          # Smart caching system
│   ├── converter.py      # Markdown/CSV conversion
│   ├── gdocs.py          # Google Docs API
│   ├── gdrive.py         # Google Drive API
│   ├── mermaid_api.py    # Mermaid diagram rendering
│   └── sync.py           # Core sync logic
├── sync_to_google.py     # Entry point
└── examples/             # Example configurations
```

## Commit Messages

- Use present tense ("Add feature" not "Added feature")
- Use imperative mood ("Move cursor to..." not "Moves cursor to...")
- Limit first line to 72 characters

## Questions?

Feel free to open an issue with the `question` label.
