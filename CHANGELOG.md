# Changelog

All notable changes to Drive Sync will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.1.0] - 2026-02-08

### Added
- `pyproject.toml` as single source of truth for project config
- `requirements-dev.txt` for test/lint dependencies (ruff, pytest-cov, pytest-xdist)
- Comprehensive test suite with 92% coverage (304 tests across 13 files)
- Type hints on all public functions (Python 3.11+ modern syntax)
- Google-style docstrings on all public classes and methods
- GitHub Actions CI with ruff linting and pytest across Python 3.11-3.13
- GitHub Actions release workflow for automatic version tagging
- ASCII wireframe rendering (`ascii_renderer.py`)
- Code syntax highlighting with Pygments (`code_renderer.py`)
- `examples/` directory with configuration and integration templates
- `CONTRIBUTING.md` with development setup and guidelines

### Changed
- Decomposed `sync.py` (1,052 lines) into `sync/` package (orchestrator, processors, uploaders)
- Consolidated 3 separate auth flows into single `GoogleAuthenticator` with lazy initialization
- Replaced print statements with logging module in `cache.py`
- Extracted magic numbers to named constants in `mermaid_api.py`
- Updated linting from flake8 to ruff

### Fixed
- Dead import (`style_orchestrator`) removed
- Bare except clause in `mermaid_api.py` replaced with specific exception handling
- Exposed API key removed from `.env.example`

### Removed
- Trivial wrapper functions in `mermaid_api.py`
- Unused `shared_drive_id` parameter from `gdrive.py` functions

## [0.4.0] - 2025-12-10

### Added
- Anchor link conversion for Google Docs headings

## [0.3.0] - 2025-12-10

### Added
- Local image embedding support for Google Docs
- Hybrid Mermaid diagram embedding strategy (local CLI + API fallback)

## [0.2.0] - 2025-11-06

### Added
- Mermaid diagram rendering via mermaid.ink API
- Zero-dependency approach (no Node.js required for API mode)

## [0.1.0] - 2025-10-30

### Added
- Initial release with core sync functionality
- Google Drive folder sync with markdown-to-Google Docs conversion
- CSV-to-Google Sheets conversion
- Smart caching to avoid unnecessary re-uploads
- Glob pattern support for `SYNC_PATHS`

---

**Repository**: https://github.com/projectassistant-webdev/drive-sync
**Issues**: https://github.com/projectassistant-webdev/drive-sync/issues
