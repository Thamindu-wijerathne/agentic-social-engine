import json
import logging
from typing import Any

import requests
from langchain.tools import tool

from config.settings import settings

logger = logging.getLogger(__name__)


def _normalize_article(article: dict[str, Any]) -> dict[str, Any]:
    source = article.get("source") or {}
    return {
        "title": article.get("title"),
        "description": article.get("description"),
        "url": article.get("url"),
        "image": article.get("image"),
        "publishedAt": article.get("publishedAt"),
        "source": {
            "name": source.get("name"),
            "url": source.get("url"),
        },
    }


@tool
def gnews_tool(max_items: int = 30, category: str = "nation") -> str:
    """Fetch top US headlines from GNews (politics/public-affairs oriented defaults)."""
    url = "https://gnews.io/api/v4/top-headlines"
    params = {
        "category": category,
        "lang": "en",
        "country": "us",
        "max": max(1, min(max_items, 100)),
        "apikey": settings.GNEWS_API_KEY,
    }

    logger.info("gnews_tool request category=%s max=%s", params["category"], params["max"])
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        logger.warning("gnews_tool request failed: %s", exc)
        return json.dumps({"error": str(exc), "articles": []})

    info = payload.get("information", {})
    realtime_message = info.get("realTimeArticles", {}).get("message")
    articles = payload.get("articles", [])
    normalized = [_normalize_article(item) for item in articles if isinstance(item, dict)]

    result = {
        "source": "gnews",
        "real_time_info": realtime_message,
        "total_articles": payload.get("totalArticles"),
        "articles": normalized,
    }
    logger.info("gnews_tool received articles=%d", len(normalized))
    return json.dumps(result)