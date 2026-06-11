import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.agents.content_writer_agent import TEMP_CONTENT_DIR
from app.connectors.fb_connector import FacebookConnector, FacebookConnectorError

logger = logging.getLogger(__name__)

TEMP_PUBLISHED_DIR = Path(__file__).resolve().parent.parent.parent / "temp" / "published"


class PublishingAgent:
    def __init__(self):
        self.facebook = FacebookConnector()

    def _build_message(self, item: dict[str, Any]) -> str:
        title = str(item.get("title", "")).strip()
        description = str(item.get("description", "")).strip()
        if title and description:
            return f"{title}\n\n{description}"
        return title or description

    def publish_item(self, item: dict[str, Any]) -> dict[str, Any]:
        title = str(item.get("title", "")).strip()
        if not title:
            raise ValueError("content item must include a title")

        picture_url = str(item.get("picture_url", "")).strip() or None
        logger.info("PublishingAgent publish_item title=%r", title[:80])

        try:
            fb_response = self.facebook.post_content(
                title=title,
                description=str(item.get("description", "")),
                picture_url=picture_url,
            )
            return {
                "status": "published",
                "title": title,
                "picture_url": picture_url,
                "category": item.get("category"),
                "facebook_post_id": fb_response.get("id"),
                "facebook_response": fb_response,
            }
        except FacebookConnectorError as exc:
            logger.warning("PublishingAgent failed title=%r error=%s", title[:80], exc)
            return {
                "status": "failed",
                "title": title,
                "picture_url": picture_url,
                "category": item.get("category"),
                "error": str(exc),
            }

    def _save_publish_log(self, batch_id: str, results: list[dict[str, Any]]) -> dict[str, Any]:
        publish_batch_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        batch_dir = TEMP_PUBLISHED_DIR / publish_batch_id
        batch_dir.mkdir(parents=True, exist_ok=True)

        published_count = sum(1 for r in results if r.get("status") == "published")
        manifest = {
            "publish_batch_id": publish_batch_id,
            "source_batch_id": batch_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "total": len(results),
            "published": published_count,
            "failed": len(results) - published_count,
            "results": results,
        }
        manifest_path = batch_dir / "publish_manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        logger.info(
            "PublishingAgent saved log batch=%s published=%d/%d",
            publish_batch_id,
            published_count,
            len(results),
        )
        return {
            "publish_batch_id": publish_batch_id,
            "saved_dir": str(batch_dir),
            "manifest_path": str(manifest_path),
            "total": len(results),
            "published": published_count,
            "failed": len(results) - published_count,
            "results": results,
        }

    def _load_items_from_batch(self, batch_id: str) -> tuple[str, list[dict[str, Any]]]:
        manifest_path = TEMP_CONTENT_DIR / batch_id / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"Content batch not found: {batch_id}")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        items = manifest.get("items", [])
        if not items:
            raise ValueError(f"Content batch {batch_id} has no items")
        return batch_id, items

    def publish_items(
        self,
        items: list[dict[str, Any]],
        source_batch_id: str | None = None,
    ) -> dict[str, Any]:
        logger.info("PublishingAgent publish_items count=%d", len(items))
        results = [self.publish_item(item) for item in items]
        return self._save_publish_log(source_batch_id or "inline", results)

    def publish_batch(self, batch_id: str) -> dict[str, Any]:
        logger.info("PublishingAgent publish_batch batch_id=%s", batch_id)
        source_batch_id, items = self._load_items_from_batch(batch_id)
        return self.publish_items(items, source_batch_id=source_batch_id)
