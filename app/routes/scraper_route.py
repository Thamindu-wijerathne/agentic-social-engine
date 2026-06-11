import logging

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, HttpUrl

from app.tools.scraper.browser_scraper import crawl_react_listing
from app.tools.scraper.web_scraper import scrape_url, to_article_payload

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/scraper", tags=["scraper"])


class ScrapeRequest(BaseModel):
    url: HttpUrl


class CrawlRequest(BaseModel):
    start_url: HttpUrl
    list_item_selector: str = Field(
        default='a[href^="/articles/"]',
        description=(
            "CSS selector for article links on the listing page. "
            "Use a[href^=\"/articles/\"] when each item is <a href=\"/articles/...\">."
        ),
        examples=['a[href^="/articles/"]', "div.news-card"],
    )
    next_page_selector: str | None = Field(
        default="a.w-pagination-next, button:has-text('Next'), a:has-text('Next'), [aria-label='Next page']",
        description="CSS selector for the bottom next-page control",
    )
    link_selector: str | None = Field(
        default=None,
        description=(
            "Link inside each card (e.g. a[href^=\"/articles/\"]). "
            "Leave null when list_item_selector already matches the <a> tag."
        ),
    )
    content_selector: str | None = Field(
        default=None,
        description="Optional CSS selector for article body/title on detail pages",
    )
    max_pages: int = Field(default=3, ge=1, le=20)
    max_items_per_page: int | None = Field(default=None, ge=1, le=50)
    headless: bool = True
    wait_ms: int = Field(default=1500, ge=0, le=10_000)


@router.post("/scrape")
def scrape_page(body: ScrapeRequest):
    url = str(body.url)
    logger.info("/scraper/scrape handler start url=%s", url)
    try:
        result = scrape_url(url)
    except requests.RequestException as exc:
        logger.warning("/scraper/scrape failed url=%s error=%s", url, exc)
        raise HTTPException(status_code=400, detail=f"Failed to scrape URL: {exc}") from exc

    logger.info("/scraper/scrape handler done url=%s", url)
    return to_article_payload(result)


@router.post("/crawl")
def crawl_pages(body: CrawlRequest):
    logger.info(
        "/scraper/crawl handler start url=%s list_item=%s max_pages=%d",
        body.start_url,
        body.list_item_selector,
        body.max_pages,
    )
    try:
        articles = crawl_react_listing(
            start_url=str(body.start_url),
            list_item_selector=body.list_item_selector,
            next_page_selector=body.next_page_selector,
            link_selector=body.link_selector,
            content_selector=body.content_selector,
            max_pages=body.max_pages,
            max_items_per_page=body.max_items_per_page,
            headless=body.headless,
            wait_ms=body.wait_ms,
        )
    except Exception as exc:
        logger.warning("/scraper/crawl failed url=%s error=%s", body.start_url, exc)
        raise HTTPException(status_code=400, detail=f"Crawl failed: {exc}") from exc

    logger.info("/scraper/crawl handler done articles=%d", len(articles))
    return {"count": len(articles), "articles": articles}
