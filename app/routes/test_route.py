import logging
from typing import Any

from fastapi import APIRouter, Body

from app.agents.content_writer_agent import ContentWriterAgent
from app.agents.reseach_agent import ReseachAgent
from app.agents.trend_agent import TrendAgent

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/test")
def test():
    logger.info("/test handler start")
    trend_agent = TrendAgent()
    response = trend_agent.run_agent(
        "Build today's topic list for older US adults with exactly 5 items: "
        "2 politics/public-affairs, 1 health, and 2 animal stories. "
        "Use gnews_tool for politics and health, and animal_news_scraper_tool for animals."
    )
    logger.info("/test handler done response_type=%s", type(response).__name__)
    return response


@router.post("/reseach-test")
def reseach_test(trends: list[dict[str, Any]] = Body(...)):
    logger.info("/reseach-test handler start trends=%d", len(trends))
    reseach_agent = ReseachAgent()
    response = reseach_agent.reseach_trends(trends)
    logger.info("/reseach-test handler done")
    return response


@router.post("/content-writer-test")
def content_writer_test(research_items: list[dict[str, Any]] = Body(...)):
    logger.info("/content-writer-test handler start items=%d", len(research_items))
    content_writer = ContentWriterAgent()
    response = content_writer.write_content(research_items)
    logger.info("/content-writer-test handler done batch_id=%s", response.get("batch_id"))
    return response
