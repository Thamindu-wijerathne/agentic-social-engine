import json
import logging

from langchain.tools import tool

from app.tools.scraper.browser_scraper import crawl_react_listing

logger = logging.getLogger(__name__)

GOOD_GOOD_GOOD_ANIMALS_URL = "https://www.goodgoodgood.co/impact/animals"
ARTICLE_LINK_SELECTOR = 'a[href^="/articles/"]'
NEXT_PAGE_SELECTOR = "a.w-pagination-next"


@tool
def animal_news_scraper_tool(max_items: int = 2) -> str:
    """Scrape positive animal news articles from Good Good Good (goodgoodgood.co/impact/animals).

    Returns article title, description, context, url, and image urls.
    Use this for the animal-news portion of the daily topic mix.
    """
    max_items = max(1, min(max_items, 10))
    logger.info("animal_news_scraper_tool start max_items=%d", max_items)

    try:
        articles = crawl_react_listing(
            start_url=GOOD_GOOD_GOOD_ANIMALS_URL,
            list_item_selector=ARTICLE_LINK_SELECTOR,
            next_page_selector=NEXT_PAGE_SELECTOR,
            link_selector=None,
            max_pages=1,
            max_items_per_page=max_items,
            headless=True,
            wait_ms=1500,
        )
    except Exception as exc:
        logger.warning("animal_news_scraper_tool failed: %s", exc)
        return json.dumps({"source": "goodgoodgood_animals", "category": "animals", "error": str(exc), "articles": []})

    normalized = []
    for article in articles:
        img_urls = article.get("img_urls") or []
        normalized.append(
            {
                "title": article.get("topic"),
                "description": article.get("description"),
                "context": article.get("context"),
                "url": article.get("url"),
                "image": img_urls[0] if img_urls else None,
                "images": img_urls,
                "source": {"name": "Good Good Good", "url": GOOD_GOOD_GOOD_ANIMALS_URL},
                "category": "animals",
            }
        )

    result = {
        "source": "goodgoodgood_animals",
        "category": "animals",
        "total_articles": len(normalized),
        "articles": normalized,
    }
    logger.info("animal_news_scraper_tool complete articles=%d", len(normalized))
    return json.dumps(result)
