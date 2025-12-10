"""
Mermaid diagram rendering using mermaid.ink API.

Zero dependencies - no Node.js, no Puppeteer, no CLI tools needed!
Uses synchronous httpx for simpler integration.
"""

import base64
import logging
import httpx

logger = logging.getLogger(__name__)


class MermaidAPIError(Exception):
    """Raised when Mermaid.ink API fails"""
    pass


def render_mermaid_diagram(
    diagram_code: str,
    format: str = "png",
    theme: str = "default",
    background_color: str = "white",
    timeout: int = 30
) -> bytes:
    """
    Render Mermaid diagram using mermaid.ink API.

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

    Example:
        >>> code = '''
        ... graph TD
        ...     A[Start] --> B[Process]
        ...     B --> C[End]
        ... '''
        >>> png_bytes = render_mermaid_diagram(code)
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
    except MermaidAPIError as e:
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
