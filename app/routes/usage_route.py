import logging

from fastapi import APIRouter, HTTPException, Query

from app.connectors.supabase_connector import get_supabase_connector
from app.repositories.token_usage_repository import TokenUsageRepositoryError, get_token_usage_repository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/usage", tags=["usage"])


@router.get(
    "/logs",
    summary="List token usage logs",
    description=(
        "List LLM token usage and estimated cost records saved after pipeline runs.\n\n"
        "Requires Supabase. Filter by `run_source` (e.g. `pipeline` or `test_pipeline`)."
    ),
)
def list_token_usage_logs(
    limit: int = Query(default=50, ge=1, le=200, description="Max rows to return"),
    run_source: str | None = Query(
        default=None,
        description="Filter by run source: pipeline, test_pipeline, etc.",
    ),
):
    if not get_supabase_connector():
        raise HTTPException(status_code=503, detail="Supabase is not configured")

    repo = get_token_usage_repository()
    if not repo:
        raise HTTPException(status_code=503, detail="Supabase is not configured")

    logger.info("/usage/logs limit=%d run_source=%s", limit, run_source)
    try:
        logs = repo.list_logs(limit=limit, run_source=run_source)
    except TokenUsageRepositoryError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    total_cost = sum(float(row.get("estimated_cost_usd") or 0) for row in logs)
    return {
        "count": len(logs),
        "total_estimated_cost_usd": round(total_cost, 6),
        "items": logs,
    }


@router.get(
    "/logs/{log_id}",
    summary="Get token usage log",
    description="Fetch one token usage log by Supabase row id, including per-agent token breakdown.",
)
def get_token_usage_log(log_id: str):
    repo = get_token_usage_repository()
    if not repo:
        raise HTTPException(status_code=503, detail="Supabase is not configured")

    try:
        log = repo.get_log(log_id)
    except TokenUsageRepositoryError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if not log:
        raise HTTPException(status_code=404, detail=f"Token usage log not found: {log_id}")
    return log
