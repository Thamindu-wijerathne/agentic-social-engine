import logging
from datetime import datetime, timezone
from typing import Any

from app.connectors.supabase_connector import SupabaseConnector, SupabaseConnectorError, get_supabase_connector

logger = logging.getLogger(__name__)

TABLE_NAME = "published_posts"


class PublishedPostsRepositoryError(Exception):
    pass


class PublishedPostsRepository:
    def __init__(self, connector: SupabaseConnector | None = None):
        self.connector = connector or get_supabase_connector()
        if not self.connector:
            raise PublishedPostsRepositoryError("Supabase is not configured")

    def insert_post(self, record: dict[str, Any]) -> dict[str, Any]:
        try:
            row = self.connector.insert(TABLE_NAME, record)
        except SupabaseConnectorError as exc:
            raise PublishedPostsRepositoryError(str(exc)) from exc
        logger.info("Supabase saved facebook_post_id=%s", record.get("facebook_post_id"))
        return row

    def list_posts(self, limit: int = 50, status: str | None = None) -> list[dict[str, Any]]:
        filters = {"status": status} if status else None
        return self.connector.select(
            TABLE_NAME,
            filters=filters,
            order_by="published_at",
            descending=True,
            limit=limit,
        )

    def get_by_facebook_post_id(self, facebook_post_id: str) -> dict[str, Any] | None:
        return self.connector.select_one(
            TABLE_NAME,
            filters={"facebook_post_id": facebook_post_id},
        )

    def mark_deleted(self, facebook_post_id: str) -> dict[str, Any]:
        payload = {
            "status": "deleted",
            "deleted_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            row = self.connector.update(
                TABLE_NAME,
                values=payload,
                filters={"facebook_post_id": facebook_post_id},
            )
        except SupabaseConnectorError as exc:
            raise PublishedPostsRepositoryError(str(exc)) from exc
        logger.info("Supabase marked deleted facebook_post_id=%s", facebook_post_id)
        return row


def get_published_posts_repository() -> PublishedPostsRepository | None:
    try:
        return PublishedPostsRepository()
    except PublishedPostsRepositoryError as exc:
        logger.warning("PublishedPostsRepository unavailable: %s", exc)
        return None
