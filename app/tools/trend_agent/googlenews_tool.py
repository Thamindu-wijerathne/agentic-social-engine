import logging
import xml.etree.ElementTree as ET

import requests
from langchain.tools import tool
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en"
# Fallback when Google blocks or drops the connection
BBC_WORLD_RSS_URL = "http://feeds.bbci.co.uk/news/world/rss.xml"

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _http_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(_BROWSER_HEADERS)
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=["GET"],
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    return session


def _fetch_rss(url: str, session: requests.Session) -> str:
    logger.info("Fetching RSS url=%s", url)
    response = session.get(url, timeout=30)
    logger.info("RSS response url=%s status=%s bytes=%d", url, response.status_code, len(response.content))
    response.raise_for_status()
    return response.text


def _summarize_rss(xml_text: str, source: str, max_items: int = 15) -> str:
    """Return a compact headline list so the LLM is not flooded with raw XML."""
    root = ET.fromstring(xml_text)
    items = root.findall(".//item")
    if not items:
        # Atom feeds use entry instead of item
        items = root.findall(".//{*}entry")

    lines = [f"Source: {source}", f"Headlines ({min(len(items), max_items)} shown):"]
    for item in items[:max_items]:
        title = item.findtext("title") or item.findtext("{*}title") or "(no title)"
        link = item.findtext("link") or item.findtext("{*}link") or ""
        pub = item.findtext("pubDate") or item.findtext("{*}published") or ""
        lines.append(f"- {title.strip()}")
        if link:
            lines.append(f"  {link.strip()}")
        if pub:
            lines.append(f"  {pub.strip()}")
    return "\n".join(lines)


@tool
def googlenews_tool() -> str:
    """Get the latest top headlines from Google News (BBC World RSS as fallback)."""
    session = _http_session()
    errors: list[str] = []

    for url, label in (
        (GOOGLE_NEWS_RSS_URL, "Google News"),
        (BBC_WORLD_RSS_URL, "BBC World News"),
    ):
        try:
            xml_text = _fetch_rss(url, session)
            return _summarize_rss(xml_text, label)
        except requests.RequestException as exc:
            msg = f"{label} ({url}): {exc}"
            logger.warning("googlenews_tool fetch failed: %s", msg)
            errors.append(msg)

    return "Could not fetch news feeds.\n" + "\n".join(errors)
