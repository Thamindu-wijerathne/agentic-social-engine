import logging
from typing import Any

from app.connectors.supabase_connector import SupabaseConnector, SupabaseConnectorError, get_supabase_connector

logger = logging.getLogger(__name__)

TABLE_NAME = "token_usage_logs"


class TokenUsageRepositoryError(Exception):
    pass


class TokenUsageRepository:
    def __init__(self, connector: SupabaseConnector | None = None):
        self.connector = connector or get_supabase_connector()
        if not self.connector:
            raise TokenUsageRepositoryError("Supabase is not configured")

    def insert_log(self, record: dict[str, Any]) -> dict[str, Any]:
        try:
            row = self.connector.insert(TABLE_NAME, record)
        except SupabaseConnectorError as exc:
            raise TokenUsageRepositoryError(str(exc)) from exc
        logger.info(
            "Supabase saved token_usage run_source=%s cost_usd=%s",
            record.get("run_source"),
            record.get("estimated_cost_usd"),
        )
        return row

    def list_logs(self, limit: int = 50, run_source: str | None = None) -> list[dict[str, Any]]:
        filters = {"run_source": run_source} if run_source else None
        return self.connector.select(
            TABLE_NAME,
            filters=filters,
            order_by="created_at",
            descending=True,
            limit=limit,
        )

    def get_log(self, log_id: str) -> dict[str, Any] | None:
        return self.connector.select_one(TABLE_NAME, filters={"id": log_id})


def get_token_usage_repository() -> TokenUsageRepository | None:
    try:
        return TokenUsageRepository()
    except TokenUsageRepositoryError as exc:
        logger.warning("TokenUsageRepository unavailable: %s", exc)
        return None


def save_token_usage_log(
    token_usage: dict[str, Any],
    *,
    run_source: str = "pipeline",
    content_batch_id: str | None = None,
    publish_batch_id: str | None = None,
    pipeline_steps: list[str] | None = None,
    trends_count: int = 0,
    research_count: int = 0,
    content_count: int = 0,
    published_count: int = 0,
    model: str | None = None,
    publish_dry_run: bool = False,
) -> dict[str, Any] | None:
    repo = get_token_usage_repository()
    if not repo:
        return None

    record = {
        "run_source": run_source,
        "content_batch_id": content_batch_id,
        "publish_batch_id": publish_batch_id,
        "pipeline_steps": pipeline_steps,
        "trends_count": trends_count,
        "research_count": research_count,
        "content_count": content_count,
        "published_count": published_count,
        "by_agent": token_usage.get("by_agent", {}),
        "total": token_usage.get("total", {}),
        "estimated_cost_usd": token_usage.get("estimated_cost_usd"),
        "model": model,
        "publish_dry_run": publish_dry_run,
    }
    try:
        return repo.insert_log(record)
    except TokenUsageRepositoryError as exc:
        logger.error(
            "Failed to save token usage log run_source=%s: %s",
            run_source,
            exc,
        )
        return None
