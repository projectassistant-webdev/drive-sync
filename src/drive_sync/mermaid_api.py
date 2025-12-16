"""
Mermaid diagram rendering with multiple backends:
1. Local mermaid-cli (mmdc) - preferred, reliable, no external dependencies
2. mermaid.ink API - fallback when CLI unavailable

The render mode is controlled by MERMAID_RENDER_MODE environment variable:
- "local" (default): Use mermaid-cli for reliable local rendering
- "api": Use mermaid.ink API (original behavior)
- "hybrid": Try local first, fall back to API on failure
"""

import base64
import logging
import os
import subprocess
import tempfile
import shutil
from pathlib import Path
import httpx

logger = logging.getLogger(__name__)

# Check if mermaid-cli is available
MMDC_AVAILABLE = shutil.which('mmdc') is not None


class MermaidAPIError(Exception):
    """Raised when Mermaid.ink API fails"""
    pass


class MermaidCLIError(Exception):
    """Raised when mermaid-cli (mmdc) fails"""
    pass


def render_mermaid_local(
    diagram_code: str,
    format: str = "png",
    theme: str = "default",
    background_color: str = "white",
    timeout: int = 60
) -> bytes:
    """
    Render Mermaid diagram using local mermaid-cli (mmdc).

    This is more reliable than the API as it:
    - Has no external network dependencies
    - No URL length limits
    - No rate limiting
    - Consistent rendering

    Args:
        diagram_code: Mermaid diagram syntax
        format: Output format (png, svg, pdf)
        theme: Mermaid theme (default, dark, forest, neutral)
        background_color: Background color
        timeout: Render timeout in seconds

    Returns:
        bytes: Rendered diagram image

    Raises:
        MermaidCLIError: If CLI rendering fails
    """
    if not MMDC_AVAILABLE:
        raise MermaidCLIError("mermaid-cli (mmdc) is not installed or not in PATH")

    # Create temp files for input and output
    temp_dir = Path(tempfile.gettempdir()) / "mermaid"
    temp_dir.mkdir(exist_ok=True)

    # Use unique filenames based on content hash
    import hashlib
    content_hash = hashlib.md5(diagram_code.encode()).hexdigest()[:8]
    input_file = temp_dir / f"diagram_{content_hash}.mmd"
    output_file = temp_dir / f"diagram_{content_hash}.{format}"

    try:
        # Write diagram code to temp file
        input_file.write_text(diagram_code, encoding='utf-8')

        # Build mmdc command
        cmd = [
            'mmdc',
            '-i', str(input_file),
            '-o', str(output_file),
            '-t', theme,
            '-b', background_color,
            '--quiet'  # Suppress progress output
        ]

        # Add puppeteer config for headless Chrome in Docker
        puppeteer_config = {
            "executablePath": os.environ.get('PUPPETEER_EXECUTABLE_PATH', '/usr/bin/chromium'),
            "args": ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        }

        # Write puppeteer config to temp file
        config_file = temp_dir / f"puppeteer_{content_hash}.json"
        import json
        config_file.write_text(json.dumps(puppeteer_config), encoding='utf-8')
        cmd.extend(['-p', str(config_file)])

        logger.info(f"Rendering Mermaid diagram via CLI (format={format}, theme={theme})")

        # Execute mermaid-cli
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )

        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or "Unknown error"
            raise MermaidCLIError(f"mmdc failed: {error_msg}")

        # Read output file
        if not output_file.exists():
            raise MermaidCLIError(f"Output file not created: {output_file}")

        image_bytes = output_file.read_bytes()
        logger.info(f"Successfully rendered Mermaid diagram via CLI ({len(image_bytes)} bytes)")

        return image_bytes

    except subprocess.TimeoutExpired:
        raise MermaidCLIError(f"Mermaid CLI timed out after {timeout}s")
    except Exception as e:
        if isinstance(e, MermaidCLIError):
            raise
        raise MermaidCLIError(f"Failed to render diagram: {e}") from e
    finally:
        # Clean up temp files
        for f in [input_file, output_file, config_file if 'config_file' in dir() else None]:
            if f and f.exists():
                try:
                    f.unlink()
                except:
                    pass


def render_mermaid_api(
    diagram_code: str,
    format: str = "png",
    theme: str = "default",
    background_color: str = "white",
    timeout: int = 30
) -> bytes:
    """
    Render Mermaid diagram using mermaid.ink API.

    Note: This function is now named render_mermaid_api. The main entry point
    is render_mermaid_diagram() which selects the appropriate backend.

    Args:
        diagram_code: Mermaid diagram syntax
        format: Output format (png, svg, pdf)
        theme: Mermaid theme (default, dark, forest, neutral)
        background_color: Background color (transparent, white, etc.)
        timeout: Request timeout in seconds

    Returns:
        bytes: Rendered diagram image

    Raises:
        MermaidAPIError: If API request fails
    """
    try:
        # Encode diagram code to base64
        graphbytes = diagram_code.encode("utf-8")
        base64_string = base64.urlsafe_b64encode(graphbytes).decode("ascii")

        # Build API URL with parameters
        url = f"https://mermaid.ink/img/{base64_string}"
        params = {
            "type": format,
            "theme": theme,
            "bgColor": background_color
        }

        logger.info(f"Rendering Mermaid diagram via API (format={format}, theme={theme})")

        # Call mermaid.ink API (synchronous for simpler integration)
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url, params=params)
            response.raise_for_status()

            image_bytes = response.content
            logger.info(f"Successfully rendered Mermaid diagram ({len(image_bytes)} bytes)")

            return image_bytes

    except httpx.HTTPError as e:
        error_msg = f"Mermaid.ink API request failed: {str(e)}"
        logger.error(error_msg)
        raise MermaidAPIError(error_msg) from e

    except Exception as e:
        error_msg = f"Failed to render Mermaid diagram: {str(e)}"
        logger.error(error_msg)
        raise MermaidAPIError(error_msg) from e


def render_mermaid_diagram(
    diagram_code: str,
    format: str = "png",
    theme: str = "default",
    background_color: str = "white",
    timeout: int = 60
) -> bytes:
    """
    Main entry point for rendering Mermaid diagrams.

    Selects rendering backend based on MERMAID_RENDER_MODE environment variable:
    - "local" (default): Use mermaid-cli for reliable local rendering
    - "api": Use mermaid.ink API (original behavior, less reliable)
    - "hybrid": Try local first, fall back to API on failure

    Args:
        diagram_code: Mermaid diagram syntax
        format: Output format (png, svg, pdf)
        theme: Mermaid theme (default, dark, forest, neutral)
        background_color: Background color
        timeout: Render timeout in seconds

    Returns:
        bytes: Rendered diagram image

    Raises:
        MermaidAPIError or MermaidCLIError: If rendering fails

    Example:
        >>> code = '''
        ... graph TD
        ...     A[Start] --> B[Process]
        ...     B --> C[End]
        ... '''
        >>> png_bytes = render_mermaid_diagram(code)
    """
    render_mode = os.environ.get('MERMAID_RENDER_MODE', 'local').lower()

    if render_mode == 'api':
        # Use API only
        logger.info("Using mermaid.ink API (MERMAID_RENDER_MODE=api)")
        return render_mermaid_api(diagram_code, format, theme, background_color, min(timeout, 30))

    elif render_mode == 'local':
        # Use local CLI only
        if not MMDC_AVAILABLE:
            raise MermaidCLIError(
                "MERMAID_RENDER_MODE=local but mermaid-cli (mmdc) is not available. "
                "Install it with: npm install -g @mermaid-js/mermaid-cli"
            )
        logger.info("Using local mermaid-cli (MERMAID_RENDER_MODE=local)")
        return render_mermaid_local(diagram_code, format, theme, background_color, timeout)

    elif render_mode == 'hybrid':
        # Try local first, fall back to API
        logger.info("Using hybrid mode (MERMAID_RENDER_MODE=hybrid)")

        if MMDC_AVAILABLE:
            try:
                return render_mermaid_local(diagram_code, format, theme, background_color, timeout)
            except MermaidCLIError as e:
                logger.warning(f"Local rendering failed, falling back to API: {e}")
                return render_mermaid_api(diagram_code, format, theme, background_color, min(timeout, 30))
        else:
            logger.info("mermaid-cli not available, using API")
            return render_mermaid_api(diagram_code, format, theme, background_color, min(timeout, 30))

    else:
        # Unknown mode, default to local if available, otherwise API
        logger.warning(f"Unknown MERMAID_RENDER_MODE={render_mode}, defaulting to local/api")
        if MMDC_AVAILABLE:
            return render_mermaid_local(diagram_code, format, theme, background_color, timeout)
        else:
            return render_mermaid_api(diagram_code, format, theme, background_color, min(timeout, 30))


def get_mermaid_url(
    diagram_code: str,
    format: str = "png",
    theme: str = "default",
    background_color: str = "white"
) -> str:
    """
    Get Mermaid.ink public URL for diagram (without downloading).

    Args:
        diagram_code: Mermaid diagram syntax
        format: Output format (png, svg, pdf)
        theme: Mermaid theme (default, dark, forest, neutral)
        background_color: Background color (transparent, white, etc.)

    Returns:
        str: Public Mermaid.ink URL for direct embedding

    Example:
        >>> code = 'graph TD\\n    A --> B'
        >>> url = get_mermaid_url(code)
        >>> # Returns: https://mermaid.ink/img/...?type=png&theme=default&bgColor=white
    """
    # Encode diagram code to base64
    graphbytes = diagram_code.encode("utf-8")
    base64_string = base64.urlsafe_b64encode(graphbytes).decode("ascii")

    # Build public URL with parameters
    url = f"https://mermaid.ink/img/{base64_string}"
    params = f"?type={format}&theme={theme}&bgColor={background_color}"

    return url + params


def validate_mermaid_syntax(diagram_code: str) -> tuple[bool, str | None]:
    """
    Validate Mermaid diagram syntax by attempting to render.

    Args:
        diagram_code: Mermaid diagram syntax to validate

    Returns:
        tuple: (is_valid, error_message)
    """
    try:
        render_mermaid_diagram(diagram_code)
        return True, None
    except (MermaidAPIError, MermaidCLIError) as e:
        return False, str(e)


# Convenience functions for common diagram types

def render_architecture_diagram(diagram_code: str) -> bytes:
    """Render architecture diagram with default theme."""
    return render_mermaid_diagram(
        diagram_code,
        format="png",
        theme="default",
        background_color="white"
    )


def render_flowchart(diagram_code: str) -> bytes:
    """Render flowchart diagram."""
    return render_mermaid_diagram(
        diagram_code,
        format="png",
        theme="default",
        background_color="white"
    )


def render_sequence_diagram(diagram_code: str) -> bytes:
    """Render sequence diagram."""
    return render_mermaid_diagram(
        diagram_code,
        format="png",
        theme="default",
        background_color="white"
    )


def render_erd_diagram(diagram_code: str) -> bytes:
    """Render entity relationship diagram (ERD)."""
    return render_mermaid_diagram(
        diagram_code,
        format="png",
        theme="default",
        background_color="white"
    )
