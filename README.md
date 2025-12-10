# Drive Sync

Automatically sync your Markdown and CSV files to Google Drive with beautiful, auto-rendered Mermaid diagrams and embedded images.

## Features

- **Mermaid Diagram Rendering** - `mermaid` code blocks automatically rendered as PNG images and embedded in Google Docs
- **Local Image Embedding** - Images referenced in markdown (`![alt](path/to/image.png)`) are uploaded and embedded
- **Anchor Link Conversion** - Markdown anchor links (`[Section](#section-name)`) become clickable links to headings in Google Docs
- **Hybrid Embedding Strategy** - Smart URL-based or Drive-hosted embedding based on diagram complexity
- **Zero Dependencies** - Uses mermaid.ink API (no Node.js, no Puppeteer, no CLI tools needed)
- **Smart Caching** - Only syncs files that have changed (MD5 hash-based)
- **CSV to Google Sheets** - Automatically converts CSV files

## Quick Start

### 1. Google Cloud Setup

Follow the [setup instructions](#setup) below.

### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env`:

```bash
GOOGLE_DRIVE_FOLDER_ID=your-folder-id-here
SYNC_PATHS=docs,README.md
ENABLE_MERMAID=true
```

### 3. Run Sync

```bash
docker compose up
```

Your markdown files will be synced to Google Drive with Mermaid diagrams rendered as images.

## How It Works

1. **Markdown Processing** - Scans markdown for `mermaid` blocks and local image references
2. **Marker Replacement** - Replaces diagrams/images with markers (`[DIAGRAM:id]`, `[IMAGE:id]`)
3. **Upload to Google Drive** - Markdown converted to Google Doc with markers intact
4. **Diagram Rendering** - Each diagram rendered via mermaid.ink API (returns PNG)
5. **Image Embedding** - Markers replaced with inline images at exact positions

### Hybrid Embedding Strategy

For Mermaid diagrams, the tool uses a smart hybrid approach:
- **Small diagrams** (URL < 2KB): Direct mermaid.ink URL embedding
- **Large diagrams**: Upload PNG to Google Drive, then embed

This optimizes for both speed and reliability.

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GOOGLE_DRIVE_FOLDER_ID` | Yes | - | Target folder ID in Google Drive |
| `SYNC_PATHS` | No | `docs` | Comma-separated files/directories to sync |
| `ENABLE_MERMAID` | No | `true` | Enable Mermaid diagram rendering |
| `RATE_LIMIT_DELAY` | No | `0.5` | Delay between API calls (seconds) |
| `BATCH_SIZE` | No | `10` | Cache save frequency |

### Docker Compose Volumes

Mount your documentation paths in `docker-compose.yml`:

```yaml
services:
  drive-sync:
    volumes:
      - ./docs:/app/docs:ro
      - ./README.md:/app/README.md:ro
```

## Setup

### 1. Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project
3. Enable these APIs:
   - Google Drive API
   - Google Docs API
   - Google Sheets API

### 2. Service Account

1. Go to "APIs & Services" → "Credentials"
2. Create a Service Account
3. Generate a JSON key
4. Save as `credentials.json` in the project root

### 3. Google Drive Folder

1. Create or open a folder in Google Drive
2. Share it with the service account email (from `credentials.json` → `client_email`)
3. Give it "Editor" or "Manager" permissions
4. Copy the folder ID from the URL

### 4. Run

```bash
cp .env.example .env
# Edit .env with your GOOGLE_DRIVE_FOLDER_ID
docker compose up
```

## Supported Content

### Mermaid Diagrams

All Mermaid diagram types are supported:
- Flowcharts (`graph TD`, `graph LR`)
- Sequence diagrams
- Entity Relationship Diagrams (ERD)
- Class diagrams
- State diagrams
- Pie charts
- Gantt charts

### Local Images

Reference images in your markdown:

```markdown
![Architecture Diagram](./images/architecture.png)
```

Images are automatically uploaded to Google Drive and embedded in the document.

### Anchor Links

Markdown anchor links are converted to clickable internal links:

```markdown
See the [Timeline](#timeline) section for details.
```

The link will navigate to the "Timeline" heading in the Google Doc.

## Troubleshooting

### Diagrams not rendering

1. Verify `ENABLE_MERMAID=true` in `.env`
2. Test syntax at [mermaid.live](https://mermaid.live)
3. Force resync: `rm -rf cache/ && docker compose up`

### Authentication errors

1. Verify `credentials.json` exists and is valid
2. Confirm the service account has access to the target folder
3. Check that all required APIs are enabled

## License

MIT
