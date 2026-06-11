import logging
from typing import Any

from supabase import Client, create_client

from config.settings import settings

logger = logging.getLogger(__name__)


class SupabaseConnectorError(Exception):
    pass


class SupabaseConnector:
    """Supabase database connector for server-side operations."""

    def __init__(
        self,
        url: str | None = None,
        secret_key: str | None = None,
    ):
        self.url = url or settings.SUPABASE_URL
        self.secret_key = secret_key or settings.SUPABASE_SECRET_KEY

        if not self.url or not self.secret_key:
            raise SupabaseConnectorError("SUPABASE_URL and SUPABASE_SECRET_KEY must be configured")

        self.client: Client = create_client(self.url, self.secret_key)
        logger.debug("SupabaseConnector initialized url=%s", self.url)

    def insert(self, table: str, record: dict[str, Any]) -> dict[str, Any]:
        response = self.client.table(table).insert(record).execute()
        rows = response.data or []
        if not rows:
            raise SupabaseConnectorError(f"Insert into {table} returned no rows")
        return rows[0]

    def select(
        self,
        table: str,
        *,
        columns: str = "*",
        filters: dict[str, Any] | None = None,
        order_by: str | None = None,
        descending: bool = True,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        query = self.client.table(table).select(columns)
        for key, value in (filters or {}).items():
            query = query.eq(key, value)
        if order_by:
            query = query.order(order_by, desc=descending)
        if limit is not None:
            query = query.limit(limit)
        response = query.execute()
        return response.data or []

    def select_one(self, table: str, filters: dict[str, Any], columns: str = "*") -> dict[str, Any] | None:
        rows = self.select(table, columns=columns, filters=filters, limit=1)
        return rows[0] if rows else None

    def update(
        self,
        table: str,
        values: dict[str, Any],
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        query = self.client.table(table).update(values)
        for key, value in filters.items():
            query = query.eq(key, value)
        response = query.execute()
        rows = response.data or []
        if not rows:
            raise SupabaseConnectorError(f"Update on {table} returned no rows")
        return rows[0]

    def delete(self, table: str, filters: dict[str, Any]) -> list[dict[str, Any]]:
        query = self.client.table(table).delete()
        for key, value in filters.items():
            query = query.eq(key, value)
        response = query.execute()
        return response.data or []


def get_supabase_connector() -> SupabaseConnector | None:
    try:
        return SupabaseConnector()
    except SupabaseConnectorError as exc:
        logger.warning("SupabaseConnector unavailable: %s", exc)
        return None
