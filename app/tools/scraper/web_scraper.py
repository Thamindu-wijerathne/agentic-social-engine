import logging
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def _meta_content(soup: BeautifulSoup, *keys: str) -> str | None:
    for key in keys:
        tag = soup.find("meta", attrs={"name": key}) or soup.find("meta", attrs={"property": key})
        if tag and tag.get("content"):
            return str(tag["content"]).strip()
    return None


def collect_image_urls(soup: BeautifulSoup, page_url: str, limit: int = 10) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()

    for attr in ("og:image", "twitter:image"):
        value = _meta_content(soup, attr)
        if value:
            absolute = urljoin(page_url, value)
            if absolute not in seen:
                seen.add(absolute)
                urls.append(absolute)

    for img in soup.find_all("img", src=True):
        absolute = urljoin(page_url, str(img["src"]))
        if absolute.startswith("http") and absolute not in seen:
            seen.add(absolute)
            urls.append(absolute)

    return urls[:limit]


def parse_html(html: str, page_url: str, content_selector: str | None = None) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")

    title = ""
    if content_selector:
        heading = soup.select_one(content_selector)
        if heading:
            title = heading.get_text(" ", strip=True)
    if not title and soup.title:
        title = soup.title.get_text(strip=True)

    description = _meta_content(soup, "description", "og:description") or ""

    content_root = soup.select_one(content_selector) if content_selector else soup
    for tag in content_root.find_all(["script", "style", "noscript"]):
        tag.decompose()

    text = " ".join(content_root.get_text(" ", strip=True).split())
    img_urls = collect_image_urls(soup, page_url)

    return {
        "url": page_url,
        "title": title,
        "description": description,
        "context": text[:2000],
        "img_urls": img_urls,
    }


def to_article_payload(parsed: dict[str, Any]) -> dict[str, Any]:
    return {
        "topic": parsed["title"] or parsed["url"],
        "description": parsed["description"],
        "context": parsed["context"],
        "img_urls": parsed["img_urls"],
        "url": parsed["url"],
    }


def scrape_url(url: str, timeout: int = 30) -> dict[str, Any]:
    logger.info("scrape_url start url=%s", url)
    response = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
    response.raise_for_status()
    result = parse_html(response.text, url)
    logger.info(
        "scrape_url complete url=%s title_chars=%d img_urls=%d",
        url,
        len(result["title"]),
        len(result["img_urls"]),
    )
    return result
