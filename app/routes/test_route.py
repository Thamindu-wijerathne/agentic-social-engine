import logging
from typing import Any

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from app.agents.content_writer_agent import ContentWriterAgent
from app.agents.publishing_agent import PublishingAgent
from app.agents.reseach_agent import ReseachAgent
from app.agents.trend_agent import TrendAgent
from app.connectors.fb_connector import FacebookConnectorError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/test", tags=["test"])

DEFAULT_TREND_PROMPT = (
    "Build today's topic list for older US adults with exactly 5 items: "
    "2 politics/public-affairs, 1 health, and 2 animal stories. "
    "Use gnews_tool for politics and health, and animal_news_scraper_tool for animals."
)


class PipelineRequest(BaseModel):
    trend_prompt: str | None = Field(
        default=None,
        description="Optional override for the trend agent input prompt",
    )
    publish: bool = Field(
        default=False,
        description="If true, publish content to Facebook after content writer step",
    )


class PublishTestRequest(BaseModel):
    items: list[dict[str, Any]] | None = Field(
        default=None,
        description="Content items to publish (title, description, picture_url)",
    )
    batch_id: str | None = Field(
        default=None,
        description="Or publish from a saved content batch id",
        examples=["20260611_104934"],
    )


@router.get("/trend-agent")
def test_trend_agent():
    """Test TrendAgent only."""
    logger.info("/test/trend-agent start")
    trend_agent = TrendAgent()
    response = trend_agent.run_agent(DEFAULT_TREND_PROMPT)
    logger.info("/test/trend-agent done count=%d", len(response))
    return {"agent": "trend", "count": len(response), "items": response}


@router.post("/reseach-agent")
def test_reseach_agent(trends: list[dict[str, Any]] = Body(...)):
    """Test ReseachAgent only. Body: trend agent output."""
    logger.info("/test/reseach-agent start trends=%d", len(trends))
    reseach_agent = ReseachAgent()
    response = reseach_agent.reseach_trends(trends)
    logger.info("/test/reseach-agent done count=%d", len(response))
    return {"agent": "reseach", "count": len(response), "items": response}


@router.post("/content-writer-agent")
def test_content_writer_agent(research_items: list[dict[str, Any]] = Body(...)):
    """Test ContentWriterAgent only. Body: research agent output."""
    logger.info("/test/content-writer-agent start items=%d", len(research_items))
    content_writer = ContentWriterAgent()
    response = content_writer.write_content(research_items)
    logger.info("/test/content-writer-agent done batch_id=%s", response.get("batch_id"))
    return {"agent": "content_writer", **response}


@router.post("/publishing-agent")
def test_publishing_agent(body: PublishTestRequest):
    """Test PublishingAgent only. Provide items or batch_id."""
    logger.info("/test/publishing-agent start")
    if not body.items and not body.batch_id:
        raise HTTPException(status_code=400, detail="Provide either items or batch_id")

    try:
        publisher = PublishingAgent()
        if body.batch_id:
            result = publisher.publish_batch(body.batch_id)
        else:
            result = publisher.publish_items(body.items or [])
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (FacebookConnectorError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    logger.info("/test/publishing-agent done published=%d", result.get("published", 0))
    return {"agent": "publishing", **result}


@router.post("/pipeline")
def test_pipeline(body: PipelineRequest | None = None):
    """Run pipeline: Trend → Research → Content Writer → optional Publish."""
    request = body or PipelineRequest()
    trend_prompt = request.trend_prompt or DEFAULT_TREND_PROMPT
    logger.info("/test/pipeline start publish=%s", request.publish)

    trend_agent = TrendAgent()
    trends = trend_agent.run_agent(trend_prompt)
    logger.info("/test/pipeline trend done count=%d", len(trends))

    reseach_agent = ReseachAgent()
    research = reseach_agent.reseach_trends(trends)
    logger.info("/test/pipeline reseach done count=%d", len(research))

    content_writer = ContentWriterAgent()
    content = content_writer.write_content(research)
    logger.info("/test/pipeline content_writer done batch_id=%s", content.get("batch_id"))

    response: dict[str, Any] = {
        "pipeline": ["trend", "reseach", "content_writer"],
        "trends": {"count": len(trends), "items": trends},
        "research": {"count": len(research), "items": research},
        "content": content,
    }

    if request.publish:
        try:
            publisher = PublishingAgent()
            publish_result = publisher.publish_items(
                content.get("items", []),
                source_batch_id=content.get("batch_id"),
            )
            response["pipeline"].append("publishing")
            response["publishing"] = publish_result
            logger.info("/test/pipeline publish done published=%d", publish_result.get("published", 0))
        except (FacebookConnectorError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"Publishing failed: {exc}") from exc

    return response
