import logging

from fastapi import APIRouter, HTTPException

from app.pipelines.content_pipeline import PipelineProductionRequest, run_content_pipeline

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pipeline", tags=["pipeline"])


@router.post("/run")
def run_pipeline(body: PipelineProductionRequest | None = None):
    """Run production pipeline: trend → research → content → Facebook publish (scheduled)."""
    request = body or PipelineProductionRequest()
    logger.info(
        "/pipeline/run start publish=%s dry_run=%s schedule=%s",
        request.publish,
        request.publish_dry_run,
        request.schedule_posts,
    )
    try:
        result = run_content_pipeline(
            trend_prompt=request.trend_prompt,
            publish=request.publish,
            publish_dry_run=request.publish_dry_run,
            schedule_posts=request.schedule_posts,
            run_source="pipeline",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if result.get("publishing_error"):
        logger.warning("/pipeline/run publish_error=%s", result["publishing_error"])

    logger.info("/pipeline/run done steps=%s", result.get("pipeline"))
    return result
