# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2025-12-10

### Added
- **Local Image Embedding**: Images referenced in markdown (`![alt](path/to/image.png)`) are now uploaded to Google Drive and embedded in Google Docs
- **Hybrid Mermaid Embedding Strategy**: Smart selection between direct URL embedding (small diagrams) and Drive-hosted embedding (large diagrams)

### Changed
- Consolidated documentation into single README.md
- Cleaned up project structure for public release

## [0.2.0] - 2025-11-06

### Added
- **Mermaid Diagram Rendering**: `mermaid` code blocks automatically rendered as PNG images via mermaid.ink API
- **Diagram Embedding**: Rendered diagrams embedded directly in Google Docs at original positions
- **Zero Dependencies**: No Node.js, Puppeteer, or CLI tools required for diagram rendering
- Google Docs API integration for precise image placement
- Marker-based embedding system (`[DIAGRAM:id]`)

### Changed
- Rebranded from docs-sync to drive-sync
- Enhanced converter to extract and process Mermaid blocks

## [0.1.0] - 2025-10-30

### Added
- Initial release
- Sync markdown files to Google Docs
- Sync CSV files to Google Sheets
- Smart MD5 hash-based caching (skip unchanged files)
- Docker support with persistent cache volumes
- Service account authentication
- Recursive directory syncing
- Code block formatting for Google Docs
- Shared Drive support
