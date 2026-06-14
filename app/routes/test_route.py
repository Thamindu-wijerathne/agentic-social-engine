import logging
from typing import Any

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from app.agents.content_writer_agent import ContentWriterAgent
from app.agents.publishing_agent import PublishingAgent
from app.agents.research_agent import ResearchAgent
from app.agents.trend_agent import TrendAgent
from app.connectors.fb_connector import FacebookConnectorError
from app.pipelines.content_pipeline import DEFAULT_TREND_PROMPT, PipelineRequest, run_content_pipeline

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/test", tags=["test"])


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
    dry_run: bool = Field(
        default=True,
        description="If true, mock Facebook publish (no real API call)",
    )


@router.get("/trend-agent")
def test_trend_agent():
    """Test TrendAgent only."""
    logger.info("/test/trend-agent start")
    trend_agent = TrendAgent()
    response = trend_agent.run_agent(DEFAULT_TREND_PROMPT)
    logger.info("/test/trend-agent done count=%d", len(response))
    return {"agent": "trend", "count": len(response), "items": response}


@router.post("/research-agent")
def test_research_agent(trends: list[dict[str, Any]] = Body(...)):
    """Test ResearchAgent only. Body: trend agent output."""
    logger.info("/test/research-agent start trends=%d", len(trends))
    research_agent = ResearchAgent()
    response = research_agent.research_trends(trends)
    logger.info("/test/research-agent done count=%d", len(response))
    return {
        "agent": "research",
        "count": len(response),
        "items": response,
        "token_usage": research_agent.last_token_usage.to_dict(),
    }


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
        publisher = PublishingAgent(dry_run=body.dry_run)
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
    """Test full pipeline via ContentPipeline service."""
    request = body or PipelineRequest()
    logger.info("/test/pipeline start publish=%s dry_run=%s", request.publish, request.publish_dry_run)
    try:
        result = run_content_pipeline(
            trend_prompt=request.trend_prompt,
            publish=request.publish,
            publish_dry_run=request.publish_dry_run,
            schedule_posts=request.schedule_posts,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    logger.info("/test/pipeline done steps=%s", result.get("pipeline"))
    return result
