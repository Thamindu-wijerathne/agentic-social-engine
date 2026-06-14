"""Validate and normalize public image URLs for Facebook and content pipeline."""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse, urljoin

logger = logging.getLogger(__name__)

_INVALID_LITERALS = {"null", "none", "n/a", "undefined", "url1", "url2"}


def normalize_image_url(raw: str, base_url: str | None = None) -> str | None:
    cleaned = str(raw).strip().strip("\"'")
    if not cleaned:
        return None
    if cleaned.lower() in _INVALID_LITERALS:
        return None

    if base_url and not cleaned.startswith(("http://", "https://")):
        cleaned = urljoin(base_url, cleaned)

    cleaned = re.sub(r"\s+", "", cleaned)
    cleaned = cleaned.rstrip(".,);]")

    parsed = urlparse(cleaned)
    if parsed.scheme not in ("http", "https"):
        return None
    if not parsed.netloc or "." not in parsed.netloc:
        return None
    if parsed.path.endswith((".svg", ".ico")):
        return None

    return cleaned


def is_valid_public_image_url(raw: str, base_url: str | None = None) -> bool:
    return normalize_image_url(raw, base_url=base_url) is not None


def filter_public_image_urls(
    urls: list[str] | None,
    *,
    base_url: str | None = None,
) -> list[str]:
    if not urls:
        return []

    filtered: list[str] = []
    seen: set[str] = set()
    for raw in urls:
        normalized = normalize_image_url(raw, base_url=base_url)
        if not normalized:
            logger.debug("Skipped invalid image url=%r", str(raw)[:120])
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        filtered.append(normalized)
    return filtered
