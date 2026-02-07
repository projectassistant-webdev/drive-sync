"""
Tests for Mermaid diagram rendering module.

Tests render_mermaid_diagram backend selection, local CLI rendering,
API rendering, hybrid fallback, URL generation, syntax validation,
and error handling (MermaidAPIError, MermaidCLIError).
"""

import base64
from unittest.mock import MagicMock, patch

import pytest

from src.drive_sync.mermaid_api import (
    MERMAID_API_TIMEOUT,
    MERMAID_DEFAULT_SCALE,
    MERMAID_DEFAULT_TIMEOUT,
    MermaidAPIError,
    MermaidCLIError,
    get_mermaid_url,
    render_mermaid_api,
    render_mermaid_diagram,
    render_mermaid_local,
    validate_mermaid_syntax,
)

SAMPLE_DIAGRAM = "graph TD\n    A[Start] --> B[End]"


class TestRenderMermaidLocal:
    """Test local CLI (mmdc) rendering."""

    @patch("src.drive_sync.mermaid_api.MMDC_AVAILABLE", False)
    def test_raises_when_mmdc_unavailable(self):
        """Test MermaidCLIError when mmdc is not installed."""
        with pytest.raises(MermaidCLIError, match="not installed"):
            render_mermaid_local(SAMPLE_DIAGRAM)

    @patch("src.drive_sync.mermaid_api.MMDC_AVAILABLE", True)
    @patch("src.drive_sync.mermaid_api.subprocess.run")
    def test_successful_render(self, mock_run, tmp_path):
        """Test successful local rendering produces bytes."""
        # Mock subprocess success
        mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")

        # Create a fake output file that render_mermaid_local will look for
        with patch("src.drive_sync.mermaid_api.Path") as mock_path_cls:
            mock_temp_dir = MagicMock()
            mock_path_cls.return_value.__truediv__ = MagicMock(return_value=mock_temp_dir)

            # Simpler approach: mock at a higher level
            fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50

            with patch.object(
                render_mermaid_local, "__module__", "src.drive_sync.mermaid_api"
            ):
                pass

        # Use a more direct approach
        mock_run.return_value = MagicMock(returncode=0, stderr="", stdout="")

        with patch("src.drive_sync.mermaid_api.tempfile.gettempdir", return_value=str(tmp_path)):
            # Pre-create the output file the function will look for
            import hashlib
            content_hash = hashlib.md5(SAMPLE_DIAGRAM.encode()).hexdigest()[:8]
            mermaid_dir = tmp_path / "mermaid"
            mermaid_dir.mkdir(exist_ok=True)
            output_file = mermaid_dir / f"diagram_{content_hash}.png"
            output_file.write_bytes(fake_png)

            result = render_mermaid_local(SAMPLE_DIAGRAM)

            assert isinstance(result, bytes)
            assert len(result) > 0
            mock_run.assert_called_once()

    @patch("src.drive_sync.mermaid_api.MMDC_AVAILABLE", True)
    @patch("src.drive_sync.mermaid_api.subprocess.run")
    def test_cli_failure_raises_error(self, mock_run, tmp_path):
        """Test MermaidCLIError on non-zero exit code."""
        mock_run.return_value = MagicMock(returncode=1, stderr="Parse error", stdout="")

        with patch("src.drive_sync.mermaid_api.tempfile.gettempdir", return_value=str(tmp_path)):
            mermaid_dir = tmp_path / "mermaid"
            mermaid_dir.mkdir(exist_ok=True)

            with pytest.raises(MermaidCLIError, match="mmdc failed"):
                render_mermaid_local(SAMPLE_DIAGRAM)

    @patch("src.drive_sync.mermaid_api.MMDC_AVAILABLE", True)
    @patch("src.drive_sync.mermaid_api.subprocess.run")
    def test_timeout_raises_error(self, mock_run, tmp_path):
        """Test MermaidCLIError on subprocess timeout."""
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="mmdc", timeout=60)

        with patch("src.drive_sync.mermaid_api.tempfile.gettempdir", return_value=str(tmp_path)):
            mermaid_dir = tmp_path / "mermaid"
            mermaid_dir.mkdir(exist_ok=True)

            with pytest.raises(MermaidCLIError, match="timed out"):
                render_mermaid_local(SAMPLE_DIAGRAM)


class TestRenderMermaidApi:
    """Test mermaid.ink API rendering."""

    @patch("src.drive_sync.mermaid_api.httpx.Client")
    def test_successful_api_render(self, mock_client_cls):
        """Test successful API rendering returns bytes."""
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        mock_response = MagicMock()
        mock_response.content = fake_png
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = render_mermaid_api(SAMPLE_DIAGRAM)

        assert isinstance(result, bytes)
        assert result == fake_png

    @patch("src.drive_sync.mermaid_api.httpx.Client")
    def test_api_http_error_raises(self, mock_client_cls):
        """Test MermaidAPIError on HTTP failure."""
        import httpx
        mock_client = MagicMock()
        mock_client.get.side_effect = httpx.HTTPError("Connection failed")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        with pytest.raises(MermaidAPIError, match="request failed"):
            render_mermaid_api(SAMPLE_DIAGRAM)

    @patch("src.drive_sync.mermaid_api.httpx.Client")
    def test_api_unexpected_error_raises(self, mock_client_cls):
        """Test MermaidAPIError on unexpected exception."""
        mock_client = MagicMock()
        mock_client.get.side_effect = RuntimeError("Unexpected")
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        with pytest.raises(MermaidAPIError, match="Failed to render"):
            render_mermaid_api(SAMPLE_DIAGRAM)


class TestRenderMermaidDiagram:
    """Test main entry point backend selection."""

    @patch("src.drive_sync.mermaid_api.render_mermaid_api")
    def test_api_mode(self, mock_api, monkeypatch):
        """Test that MERMAID_RENDER_MODE=api uses API backend."""
        monkeypatch.setenv("MERMAID_RENDER_MODE", "api")
        mock_api.return_value = b"fake-png"

        result = render_mermaid_diagram(SAMPLE_DIAGRAM)

        assert result == b"fake-png"
        mock_api.assert_called_once()

    @patch("src.drive_sync.mermaid_api.MMDC_AVAILABLE", True)
    @patch("src.drive_sync.mermaid_api.render_mermaid_local")
    def test_local_mode(self, mock_local, monkeypatch):
        """Test that MERMAID_RENDER_MODE=local uses local backend."""
        monkeypatch.setenv("MERMAID_RENDER_MODE", "local")
        mock_local.return_value = b"fake-png"

        result = render_mermaid_diagram(SAMPLE_DIAGRAM)

        assert result == b"fake-png"
        mock_local.assert_called_once()

    @patch("src.drive_sync.mermaid_api.MMDC_AVAILABLE", False)
    def test_local_mode_without_mmdc_raises(self, monkeypatch):
        """Test that local mode raises when mmdc not available."""
        monkeypatch.setenv("MERMAID_RENDER_MODE", "local")

        with pytest.raises(MermaidCLIError, match="not available"):
            render_mermaid_diagram(SAMPLE_DIAGRAM)

    @patch("src.drive_sync.mermaid_api.MMDC_AVAILABLE", True)
    @patch("src.drive_sync.mermaid_api.render_mermaid_local")
    def test_hybrid_mode_uses_local_first(self, mock_local, monkeypatch):
        """Test hybrid mode tries local backend first."""
        monkeypatch.setenv("MERMAID_RENDER_MODE", "hybrid")
        mock_local.return_value = b"fake-png"

        result = render_mermaid_diagram(SAMPLE_DIAGRAM)

        assert result == b"fake-png"
        mock_local.assert_called_once()

    @patch("src.drive_sync.mermaid_api.MMDC_AVAILABLE", True)
    @patch("src.drive_sync.mermaid_api.render_mermaid_api")
    @patch("src.drive_sync.mermaid_api.render_mermaid_local")
    def test_hybrid_mode_falls_back_to_api(self, mock_local, mock_api, monkeypatch):
        """Test hybrid mode falls back to API when local fails."""
        monkeypatch.setenv("MERMAID_RENDER_MODE", "hybrid")
        mock_local.side_effect = MermaidCLIError("CLI failed")
        mock_api.return_value = b"api-png"

        result = render_mermaid_diagram(SAMPLE_DIAGRAM)

        assert result == b"api-png"
        mock_local.assert_called_once()
        mock_api.assert_called_once()

    @patch("src.drive_sync.mermaid_api.MMDC_AVAILABLE", False)
    @patch("src.drive_sync.mermaid_api.render_mermaid_api")
    def test_hybrid_mode_no_mmdc_uses_api(self, mock_api, monkeypatch):
        """Test hybrid mode uses API when mmdc not available."""
        monkeypatch.setenv("MERMAID_RENDER_MODE", "hybrid")
        mock_api.return_value = b"api-png"

        result = render_mermaid_diagram(SAMPLE_DIAGRAM)

        assert result == b"api-png"
        mock_api.assert_called_once()

    @patch("src.drive_sync.mermaid_api.MMDC_AVAILABLE", True)
    @patch("src.drive_sync.mermaid_api.render_mermaid_local")
    def test_unknown_mode_defaults_to_local(self, mock_local, monkeypatch):
        """Test unknown render mode defaults to local if available."""
        monkeypatch.setenv("MERMAID_RENDER_MODE", "unknown_mode")
        mock_local.return_value = b"fake-png"

        result = render_mermaid_diagram(SAMPLE_DIAGRAM)

        assert result == b"fake-png"
        mock_local.assert_called_once()

    @patch("src.drive_sync.mermaid_api.MMDC_AVAILABLE", False)
    @patch("src.drive_sync.mermaid_api.render_mermaid_api")
    def test_unknown_mode_falls_back_to_api(self, mock_api, monkeypatch):
        """Test unknown render mode uses API when mmdc unavailable."""
        monkeypatch.setenv("MERMAID_RENDER_MODE", "unknown_mode")
        mock_api.return_value = b"api-png"

        result = render_mermaid_diagram(SAMPLE_DIAGRAM)

        assert result == b"api-png"
        mock_api.assert_called_once()


class TestGetMermaidUrl:
    """Test URL generation for mermaid.ink."""

    def test_returns_url_string(self):
        """Test that a valid URL string is returned."""
        url = get_mermaid_url(SAMPLE_DIAGRAM)
        assert isinstance(url, str)
        assert url.startswith("https://mermaid.ink/img/")

    def test_url_contains_base64(self):
        """Test that URL contains base64-encoded diagram."""
        url = get_mermaid_url(SAMPLE_DIAGRAM)
        expected_b64 = base64.urlsafe_b64encode(SAMPLE_DIAGRAM.encode()).decode("ascii")
        assert expected_b64 in url

    def test_url_includes_params(self):
        """Test that URL includes format, theme, and bg params."""
        url = get_mermaid_url(SAMPLE_DIAGRAM, format="svg", theme="dark", background_color="transparent")
        assert "type=svg" in url
        assert "theme=dark" in url
        assert "bgColor=transparent" in url

    def test_default_params(self):
        """Test that default params are png, default theme, white bg."""
        url = get_mermaid_url(SAMPLE_DIAGRAM)
        assert "type=png" in url
        assert "theme=default" in url
        assert "bgColor=white" in url


class TestValidateMermaidSyntax:
    """Test Mermaid syntax validation."""

    @patch("src.drive_sync.mermaid_api.render_mermaid_diagram")
    def test_valid_syntax_returns_true(self, mock_render):
        """Test that valid syntax returns (True, None)."""
        mock_render.return_value = b"fake-png"

        is_valid, error = validate_mermaid_syntax(SAMPLE_DIAGRAM)

        assert is_valid is True
        assert error is None

    @patch("src.drive_sync.mermaid_api.render_mermaid_diagram")
    def test_invalid_syntax_returns_false(self, mock_render):
        """Test that invalid syntax returns (False, error_message)."""
        mock_render.side_effect = MermaidCLIError("Parse error")

        is_valid, error = validate_mermaid_syntax("invalid diagram")

        assert is_valid is False
        assert "Parse error" in error

    @patch("src.drive_sync.mermaid_api.render_mermaid_diagram")
    def test_api_error_returns_false(self, mock_render):
        """Test that API error returns (False, error_message)."""
        mock_render.side_effect = MermaidAPIError("API failed")

        is_valid, error = validate_mermaid_syntax("bad diagram")

        assert is_valid is False
        assert "API failed" in error


class TestMermaidExceptions:
    """Test Mermaid exception classes."""

    def test_api_error_is_exception(self):
        """Test that MermaidAPIError is an Exception subclass."""
        assert issubclass(MermaidAPIError, Exception)

    def test_cli_error_is_exception(self):
        """Test that MermaidCLIError is an Exception subclass."""
        assert issubclass(MermaidCLIError, Exception)

    def test_api_error_carries_message(self):
        """Test that MermaidAPIError carries descriptive message."""
        with pytest.raises(MermaidAPIError, match="test error"):
            raise MermaidAPIError("test error")

    def test_cli_error_carries_message(self):
        """Test that MermaidCLIError carries descriptive message."""
        with pytest.raises(MermaidCLIError, match="cli error"):
            raise MermaidCLIError("cli error")


class TestMermaidConstants:
    """Test module-level constants."""

    def test_default_timeout(self):
        """Test MERMAID_DEFAULT_TIMEOUT is 60."""
        assert MERMAID_DEFAULT_TIMEOUT == 60

    def test_api_timeout(self):
        """Test MERMAID_API_TIMEOUT is 30."""
        assert MERMAID_API_TIMEOUT == 30

    def test_default_scale(self):
        """Test MERMAID_DEFAULT_SCALE is 3."""
        assert MERMAID_DEFAULT_SCALE == 3
