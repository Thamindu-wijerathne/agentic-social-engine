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
        description="Content items to publish (title, description, picture_url).",
    )
    batch_id: str | None = Field(
        default=None,
        description="Alternatively publish from a saved content batch id.",
        examples=["20260611_104934"],
    )
    dry_run: bool = Field(
        default=True,
        description="Mock Facebook publish by default for safe local testing.",
    )


@router.get(
    "/trend-agent",
    summary="Test trend agent",
    description="Run TrendAgent only with the default daily topic prompt. Returns scored topics and token usage.",
)
def test_trend_agent():
    logger.info("/test/trend-agent start")
    trend_agent = TrendAgent()
    response = trend_agent.run_agent(DEFAULT_TREND_PROMPT)
    logger.info("/test/trend-agent done count=%d", len(response))
    return {
        "agent": "trend",
        "count": len(response),
        "items": response,
        "token_usage": trend_agent.last_token_usage.to_dict(),
    }


@router.post(
    "/research-agent",
    summary="Test research agent",
    description="Run ResearchAgent on trend output JSON. Body: array of trend topic objects from TrendAgent.",
)
def test_research_agent(trends: list[dict[str, Any]] = Body(...)):
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


@router.post(
    "/content-writer-agent",
    summary="Test content writer agent",
    description="Run ContentWriterAgent on research output. Saves posts to `temp/content/{batch_id}` when successful.",
)
def test_content_writer_agent(research_items: list[dict[str, Any]] = Body(...)):
    logger.info("/test/content-writer-agent start items=%d", len(research_items))
    content_writer = ContentWriterAgent()
    response = content_writer.write_content(research_items)
    logger.info("/test/content-writer-agent done batch_id=%s", response.get("batch_id"))
    return {"agent": "content_writer", **response}


@router.post(
    "/publishing-agent",
    summary="Test publishing agent",
    description=(
        "Run PublishingAgent in isolation. Provide `items` or `batch_id`.\n\n"
        "Defaults to `dry_run=true` so no real Facebook posts are created."
    ),
)
def test_publishing_agent(body: PublishTestRequest):
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


@router.post(
    "/pipeline",
    summary="Test full pipeline",
    description=(
        "Run the full pipeline with dev-safe defaults: `publish=false`, `publish_dry_run=false`.\n\n"
        "Set `publish=true` and `publish_dry_run=true` to test the publish step without real Facebook calls."
    ),
)
def test_pipeline(body: PipelineRequest | None = None):
    request = body or PipelineRequest()
    logger.info(
        "/test/pipeline start publish=%s dry_run=%s",
        request.publish,
        request.publish_dry_run,
    )
    try:
        result = run_content_pipeline(
            trend_prompt=request.trend_prompt,
            publish=request.publish,
            publish_dry_run=request.publish_dry_run,
            schedule_posts=request.schedule_posts,
            run_source="test_pipeline",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    logger.info("/test/pipeline done steps=%s", result.get("pipeline"))
    return result
