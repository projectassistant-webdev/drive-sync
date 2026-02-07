"""
Shared test fixtures for drive-sync test suite.

Provides reusable fixtures for:
- Mock Google API clients (Drive, Docs)
- Mock credentials and authenticator
- Sample markdown content with various embedded content types
- Temporary file/directory helpers
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_credentials():
    """Mock Google service account credentials."""
    creds = MagicMock()
    creds.token = "fake-token"
    creds.valid = True
    creds.service_account_email = "test@test-project.iam.gserviceaccount.com"
    return creds


@pytest.fixture
def mock_drive_service():
    """Mock Google Drive API v3 service.

    Preconfigured with common Drive API method chains:
    - files().list().execute()
    - files().create().execute()
    - files().update().execute()
    - permissions().create().execute()
    """
    service = MagicMock()
    # Default: empty file listing
    service.files().list().execute.return_value = {"files": []}
    # Default: successful create
    service.files().create().execute.return_value = {
        "id": "fake-file-id",
        "name": "test-file",
        "webViewLink": "https://docs.google.com/document/d/fake-file-id/edit",
        "webContentLink": "https://drive.google.com/uc?id=fake-file-id",
    }
    # Default: successful update
    service.files().update().execute.return_value = {
        "id": "fake-file-id",
        "name": "test-file",
    }
    # Default: successful permission create
    service.permissions().create().execute.return_value = {}
    return service


@pytest.fixture
def mock_docs_service():
    """Mock Google Docs API v1 service.

    Preconfigured with common Docs API method chains:
    - documents().get().execute()
    - documents().batchUpdate().execute()
    """
    service = MagicMock()
    # Default: empty document
    service.documents().get().execute.return_value = {
        "body": {"content": []}
    }
    # Default: successful batch update
    service.documents().batchUpdate().execute.return_value = {}
    return service


@pytest.fixture
def mock_authenticator(mock_credentials, mock_drive_service, mock_docs_service):
    """Mock GoogleAuthenticator with pre-configured services.

    Provides a mock authenticator that returns mock credentials and services
    without touching real Google APIs.
    """
    auth = MagicMock()
    auth.credentials_file = Path("credentials.json")
    auth.credentials = mock_credentials
    auth.drive_service = mock_drive_service
    auth.docs_service = mock_docs_service
    auth.authenticate.return_value = mock_drive_service
    auth.service = mock_drive_service
    return auth


@pytest.fixture
def sample_mermaid_code():
    """Return sample Mermaid diagram code for testing."""
    return "graph TD\n    A[Start] --> B[Process]\n    B --> C[End]"


@pytest.fixture
def sample_markdown(tmp_path):
    """Create sample markdown files with various content types.

    Returns a dict mapping content type to file path:
    - 'simple': Basic markdown
    - 'with_mermaid': Markdown with a Mermaid diagram
    - 'with_code': Markdown with code blocks
    - 'with_images': Markdown with image references
    """
    files = {}

    # Simple markdown
    simple = tmp_path / "simple.md"
    simple.write_text("# Simple Document\n\nJust some text.\n")
    files["simple"] = simple

    # Markdown with mermaid
    with_mermaid = tmp_path / "with_mermaid.md"
    with_mermaid.write_text(
        "# Diagram Doc\n\n"
        "```mermaid\n"
        "graph TD\n"
        "    A[Start] --> B[End]\n"
        "```\n"
    )
    files["with_mermaid"] = with_mermaid

    # Markdown with code blocks
    with_code = tmp_path / "with_code.md"
    with_code.write_text(
        "# Code Doc\n\n"
        "```python\n"
        "def hello():\n"
        "    print('world')\n"
        "```\n"
    )
    files["with_code"] = with_code

    # Markdown with local image reference
    img = tmp_path / "test_image.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    with_images = tmp_path / "with_images.md"
    with_images.write_text(
        "# Image Doc\n\n"
        "![Screenshot](test_image.png)\n"
    )
    files["with_images"] = with_images

    return files


@pytest.fixture
def temp_cache(tmp_path):
    """Create a SyncCache with a temporary file."""
    from src.drive_sync.cache import SyncCache

    cache_file = tmp_path / "cache" / ".test_cache.json"
    return SyncCache(cache_file=str(cache_file))


@pytest.fixture
def mock_env_vars(monkeypatch):
    """Set common environment variables for testing.

    Sets GOOGLE_DRIVE_FOLDER_ID, ENABLE_MERMAID, and MERMAID_RENDER_MODE
    so tests don't depend on the host environment.
    """
    monkeypatch.setenv("GOOGLE_DRIVE_FOLDER_ID", "fake-folder-id")
    monkeypatch.setenv("ENABLE_MERMAID", "true")
    monkeypatch.setenv("MERMAID_RENDER_MODE", "local")
    monkeypatch.setenv("ENABLE_ANCHOR_LINKS", "true")
