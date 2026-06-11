import logging

from fastapi import APIRouter, HTTPException

from app.pipelines.content_pipeline import PipelineRequest, run_content_pipeline

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pipeline", tags=["pipeline"])


@router.post("/run")
def run_pipeline(body: PipelineRequest | None = None):
    """Run full content pipeline: Trend → Research → Content Writer → optional Publish."""
    request = body or PipelineRequest()
    logger.info("/pipeline/run start publish=%s", request.publish)
    try:
        result = run_content_pipeline(
            trend_prompt=request.trend_prompt,
            publish=request.publish,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    logger.info("/pipeline/run done steps=%s", result.get("pipeline"))
    return result
