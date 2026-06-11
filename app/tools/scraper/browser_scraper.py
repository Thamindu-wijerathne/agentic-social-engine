import logging
from typing import Any

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

from app.tools.scraper.web_scraper import parse_html, to_article_payload

logger = logging.getLogger(__name__)

NAV_TIMEOUT_MS = 60_000
NAV_WAIT_UNTIL = "domcontentloaded"


def _safe_goto(page, url: str, timeout: int = NAV_TIMEOUT_MS) -> None:
    """Navigate without waiting for networkidle (hangs on analytics-heavy sites)."""
    try:
        page.goto(url, wait_until=NAV_WAIT_UNTIL, timeout=timeout)
    except PlaywrightTimeout:
        logger.warning("Navigation timeout for %s, continuing with partial page", url)


def _wait_for_listing(page, list_item_selector: str, wait_ms: int) -> None:
    page.wait_for_selector(list_item_selector, timeout=NAV_TIMEOUT_MS)
    page.wait_for_timeout(wait_ms)


def _scrape_open_page(
    page,
    content_selector: str | None,
) -> dict[str, Any]:
    html = page.content()
    parsed = parse_html(html, page.url, content_selector=content_selector)
    return to_article_payload(parsed)


def _item_detail_urls(page, list_item_selector: str, link_selector: str | None) -> list[str]:
    items = page.locator(list_item_selector)
    count = items.count()
    urls: list[str] = []

    for index in range(count):
        item = items.nth(index)
        target = item.locator(link_selector).first if link_selector else item
        href = target.get_attribute("href")
        if not href or href.startswith("#") or href.lower().startswith("javascript:"):
            continue
        urls.append(page.evaluate(
            "(href) => new URL(href, window.location.href).href",
            href,
        ))

    seen: set[str] = set()
    unique_urls: list[str] = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)
    return unique_urls


def _scrape_by_clicking_items(
    page,
    list_item_selector: str,
    content_selector: str | None,
    wait_ms: int,
    max_items_per_page: int | None,
) -> list[dict[str, Any]]:
    articles: list[dict[str, Any]] = []
    items = page.locator(list_item_selector)
    count = items.count()
    if max_items_per_page is not None:
        count = min(count, max_items_per_page)

    listing_url = page.url
    logger.info("Click-scrape page items=%d url=%s", count, listing_url)

    for index in range(count):
        try:
            item = page.locator(list_item_selector).nth(index)
            item.scroll_into_view_if_needed()
            item.click()
            page.wait_for_load_state(NAV_WAIT_UNTIL, timeout=NAV_TIMEOUT_MS)
            page.wait_for_timeout(wait_ms)

            article = _scrape_open_page(page, content_selector)
            articles.append(article)
            logger.info("Scraped item %d/%d url=%s", index + 1, count, article["url"])

            page.go_back(wait_until=NAV_WAIT_UNTIL, timeout=NAV_TIMEOUT_MS)
            _wait_for_listing(page, list_item_selector, wait_ms)
        except Exception as exc:
            logger.warning("Failed click-scrape item %d/%d: %s", index + 1, count, exc)
            _safe_goto(page, listing_url)
            _wait_for_listing(page, list_item_selector, wait_ms)

    return articles


def _scrape_by_urls(
    page,
    detail_urls: list[str],
    content_selector: str | None,
    wait_ms: int,
) -> list[dict[str, Any]]:
    articles: list[dict[str, Any]] = []
    for index, detail_url in enumerate(detail_urls, start=1):
        try:
            _safe_goto(page, detail_url)
            page.wait_for_timeout(wait_ms)
            article = _scrape_open_page(page, content_selector)
            articles.append(article)
            logger.info("Scraped url %d/%d %s", index, len(detail_urls), detail_url)
        except Exception as exc:
            logger.warning("Failed to scrape %s: %s", detail_url, exc)
    return articles


def _has_next_page(page, next_page_selector: str) -> bool:
    next_locator = page.locator(next_page_selector)
    if next_locator.count() == 0:
        return False
    next_button = next_locator.first
    if not next_button.is_visible():
        return False
    disabled = next_button.get_attribute("disabled")
    aria_disabled = next_button.get_attribute("aria-disabled")
    class_name = (next_button.get_attribute("class") or "").lower()
    return disabled is None and aria_disabled not in ("true", "1") and "disabled" not in class_name


def crawl_react_listing(
    start_url: str,
    list_item_selector: str,
    next_page_selector: str | None = None,
    link_selector: str | None = None,
    content_selector: str | None = None,
    max_pages: int = 5,
    max_items_per_page: int | None = None,
    headless: bool = True,
    wait_ms: int = 1500,
) -> list[dict[str, Any]]:
    """
    Crawl a React listing page:
    1. Open each news card (click or follow link inside card)
    2. Scrape detail page text + images
    3. Go back to listing
    4. Click bottom "next" and repeat
    """
    if max_pages < 1:
        return []

    all_articles: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    logger.info("crawl_react_listing start url=%s max_pages=%d", start_url, max_pages)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        page = browser.new_page()
        page.set_default_timeout(NAV_TIMEOUT_MS)

        try:
            _safe_goto(page, start_url)
            _wait_for_listing(page, list_item_selector, wait_ms)

            for page_index in range(max_pages):
                logger.info("Listing page %d url=%s", page_index + 1, page.url)

                detail_urls = _item_detail_urls(page, list_item_selector, link_selector)
                if detail_urls:
                    listing_url = page.url
                    page_articles = _scrape_by_urls(
                        page,
                        detail_urls[:max_items_per_page] if max_items_per_page else detail_urls,
                        content_selector,
                        wait_ms,
                    )
                    _safe_goto(page, listing_url)
                    _wait_for_listing(page, list_item_selector, wait_ms)
                else:
                    page_articles = _scrape_by_clicking_items(
                        page,
                        list_item_selector,
                        content_selector,
                        wait_ms,
                        max_items_per_page,
                    )

                for article in page_articles:
                    article_url = article["url"]
                    if article_url in seen_urls:
                        continue
                    seen_urls.add(article_url)
                    all_articles.append(article)

                if not next_page_selector or page_index + 1 >= max_pages:
                    break
                if not _has_next_page(page, next_page_selector):
                    logger.info("No next page button on page %d", page_index + 1)
                    break

                next_button = page.locator(next_page_selector).first
                next_button.scroll_into_view_if_needed()
                next_button.click()
                page.wait_for_load_state(NAV_WAIT_UNTIL, timeout=NAV_TIMEOUT_MS)
                _wait_for_listing(page, list_item_selector, wait_ms)

        except Exception as exc:
            logger.warning("crawl_react_listing error: %s", exc)
            if not all_articles:
                raise
        finally:
            browser.close()

    logger.info("crawl_react_listing complete articles=%d", len(all_articles))
    return all_articles
