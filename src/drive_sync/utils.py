"""
Utility functions for drive-sync.

Includes:
- slugify_heading: Convert heading text to markdown-compatible anchor slugs
- get_unique_slug: Handle duplicate headings with -1, -2 suffixes
"""

import re
import unicodedata
from typing import Dict


def slugify_heading(text: str) -> str:
    """
    Convert heading text to markdown-compatible anchor slug.

    Matches VS Code / CommonMark anchor generation:
    - Normalize diacritics to ASCII (é → e, ü → u)
    - Lowercase
    - Replace spaces with hyphens
    - Remove special characters (keep alphanumeric and hyphens)
    - DO NOT collapse multiple hyphens (preserves `--` from removed `&`)
    - Strip leading/trailing hyphens

    Args:
        text: Heading text to convert

    Returns:
        Slugified anchor text (e.g., "timeline--rollout-strategy")

    Examples:
        >>> slugify_heading("Timeline & Rollout Strategy")
        "timeline--rollout-strategy"
        >>> slugify_heading("Café Setup")
        "cafe-setup"
        >>> slugify_heading("🚀 Quick Start")
        "quick-start"
    """
    # Handle empty/whitespace-only input
    if not text or not text.strip():
        return ""

    # Normalize diacritics to ASCII (NFKD decomposition + ASCII encoding)
    slug = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')

    # Lowercase
    slug = slug.lower()

    # Replace spaces with hyphens
    slug = slug.replace(' ', '-')

    # Remove special characters except hyphens and alphanumeric
    # Example: "Timeline & Rollout" → "timeline--rollout" (& surrounded by spaces → --)
    slug = re.sub(r'[^a-z0-9\-]', '', slug)

    # Strip leading/trailing hyphens
    slug = slug.strip('-')

    # DO NOT collapse hyphens - VS Code preserves them
    # "Timeline & Rollout" → "timeline--rollout" (correct)

    return slug


def get_unique_slug(base_slug: str, seen_slugs: Dict[str, int]) -> str:
    """
    Get unique slug for heading, handling duplicates with -1, -2 suffixes.

    This matches VS Code / CommonMark behavior for duplicate headings:
    - First occurrence: "overview" (no suffix)
    - Second occurrence: "overview-1"
    - Third occurrence: "overview-2"

    Args:
        base_slug: Base slug from slugify_heading()
        seen_slugs: Dict tracking seen slugs (mutated in-place)

    Returns:
        Unique slug with suffix if needed

    Examples:
        >>> seen = {}
        >>> get_unique_slug("overview", seen)
        "overview"
        >>> get_unique_slug("overview", seen)
        "overview-1"
        >>> get_unique_slug("overview", seen)
        "overview-2"
    """
    if base_slug not in seen_slugs:
        seen_slugs[base_slug] = 0
        return base_slug

    seen_slugs[base_slug] += 1
    return f"{base_slug}-{seen_slugs[base_slug]}"
