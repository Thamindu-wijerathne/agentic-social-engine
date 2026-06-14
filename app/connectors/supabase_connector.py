import logging
from typing import Any
from urllib.parse import urlparse

import httpx
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
        raw_url = (url or settings.SUPABASE_URL or "").strip().rstrip("/")
        # Dashboard sometimes shows .../rest/v1 — the Python client wants the project root only.
        if raw_url.endswith("/rest/v1"):
            raw_url = raw_url[: -len("/rest/v1")].rstrip("/")
        self.url = raw_url
        self.secret_key = (secret_key or settings.SUPABASE_SECRET_KEY or "").strip()

        if not self.url or not self.secret_key:
            raise SupabaseConnectorError("SUPABASE_URL and SUPABASE_SECRET_KEY must be configured")

        parsed = urlparse(self.url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise SupabaseConnectorError(
                "SUPABASE_URL must be like https://YOUR_PROJECT_REF.supabase.co"
            )

        self.client: Client = create_client(self.url, self.secret_key)
        logger.debug("SupabaseConnector initialized host=%s", parsed.hostname)

    def _wrap_request_error(self, exc: Exception) -> SupabaseConnectorError:
        if isinstance(exc, httpx.ConnectError):
            host = urlparse(self.url).hostname or self.url
            return SupabaseConnectorError(
                f"Cannot reach Supabase at {host}. "
                "Check SUPABASE_URL in .env (Project Settings → API → Project URL)."
            )
        return SupabaseConnectorError(str(exc))

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
        try:
            response = query.execute()
        except httpx.ConnectError as exc:
            raise self._wrap_request_error(exc) from exc
        return response.data or []

    def select_one(self, table: str, filters: dict[str, Any], columns: str = "*") -> dict[str, Any] | None:
        rows = self.select(table, columns=columns, filters=filters, limit=1)
        return rows[0] if rows else None

    def insert(self, table: str, record: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self.client.table(table).insert(record).execute()
        except httpx.ConnectError as exc:
            raise self._wrap_request_error(exc) from exc
        rows = response.data or []
        if not rows:
            raise SupabaseConnectorError(f"Insert into {table} returned no rows")
        return rows[0]

    def update(
        self,
        table: str,
        values: dict[str, Any],
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        query = self.client.table(table).update(values)
        for key, value in filters.items():
            query = query.eq(key, value)
        try:
            response = query.execute()
        except httpx.ConnectError as exc:
            raise self._wrap_request_error(exc) from exc
        rows = response.data or []
        if not rows:
            raise SupabaseConnectorError(f"Update on {table} returned no rows")
        return rows[0]

    def delete(self, table: str, filters: dict[str, Any]) -> list[dict[str, Any]]:
        query = self.client.table(table).delete()
        for key, value in filters.items():
            query = query.eq(key, value)
        try:
            response = query.execute()
        except httpx.ConnectError as exc:
            raise self._wrap_request_error(exc) from exc
        return response.data or []


def get_supabase_connector() -> SupabaseConnector | None:
    try:
        return SupabaseConnector()
    except SupabaseConnectorError as exc:
        logger.warning("SupabaseConnector unavailable: %s", exc)
        return None
