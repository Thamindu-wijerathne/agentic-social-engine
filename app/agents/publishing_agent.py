import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.agents.content_writer_agent import TEMP_CONTENT_DIR
from app.connectors.fb_connector import FacebookConnector, FacebookConnectorError
from app.core.publish_schedule import compute_schedule_times, format_schedule_slot, get_schedule_timezone
from app.core.image_urls import filter_public_image_urls
from app.repositories.published_posts_repository import get_published_posts_repository

logger = logging.getLogger(__name__)

TEMP_PUBLISHED_DIR = Path(__file__).resolve().parent.parent.parent / "temp" / "published"


class PublishingAgent:
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.facebook = FacebookConnector(dry_run=dry_run)
        self.posts_repo = get_published_posts_repository()

    def _trace_post(
        self,
        *,
        facebook_post_id: str,
        title: str,
        description: str,
        picture_url: str | None,
        picture_urls: list[str] | None,
        category: str | None,
        hashtags: list[str] | None,
        content_batch_id: str | None,
        publish_batch_id: str | None,
        scheduled_publish_at: datetime | None = None,
    ) -> dict[str, Any] | None:
        if not self.posts_repo:
            return None

        is_scheduled = scheduled_publish_at is not None
        record = {
            "facebook_post_id": facebook_post_id,
            "title": title,
            "description": description,
            "picture_url": picture_url,
            "picture_urls": picture_urls or [],
            "category": category,
            "hashtags": hashtags or [],
            "content_batch_id": content_batch_id,
            "publish_batch_id": publish_batch_id,
            "status": "scheduled" if is_scheduled else "published",
            "dry_run": self.dry_run,
            "published_at": datetime.now(timezone.utc).isoformat(),
            "scheduled_publish_at": scheduled_publish_at.isoformat() if scheduled_publish_at else None,
        }
        try:
            return self.posts_repo.insert_post(record)
        except Exception as exc:
            logger.warning("Failed to trace post in Supabase title=%r error=%s", title[:80], exc)
            return None

    def publish_item(
        self,
        item: dict[str, Any],
        *,
        content_batch_id: str | None = None,
        publish_batch_id: str | None = None,
        scheduled_publish_at: datetime | None = None,
    ) -> dict[str, Any]:
        title = str(item.get("title", "")).strip()
        if not title:
            raise ValueError("content item must include a title")

        description = str(item.get("description", ""))
        picture_urls = item.get("picture_urls") or []
        if not isinstance(picture_urls, list):
            picture_urls = [picture_urls] if picture_urls else []

        picture_urls = filter_public_image_urls(picture_urls)
        picture_url = str(item.get("picture_url", "")).strip()
        if picture_url:
            primary = filter_public_image_urls([picture_url])
            if primary and primary[0] not in picture_urls:
                picture_urls.insert(0, primary[0])
            picture_url = primary[0] if primary else picture_urls[0] if picture_urls else ""
        elif picture_urls:
            picture_url = picture_urls[0]

        category = item.get("category")
        hashtags = item.get("hashtags") or []
        if not isinstance(hashtags, list):
            hashtags = [hashtags] if hashtags else []

        if not picture_urls:
            logger.warning("PublishingAgent skipped missing picture_urls title=%r", title[:80])
            return {
                "status": "failed",
                "title": title,
                "picture_url": None,
                "picture_urls": [],
                "category": category,
                "error": "picture_url is required",
            }

        scheduled_unix = int(scheduled_publish_at.timestamp()) if scheduled_publish_at else None
        if scheduled_publish_at:
            logger.info(
                "PublishingAgent schedule_item title=%r slot=%s photos=%d",
                title[:80],
                format_schedule_slot(scheduled_publish_at),
                len(picture_urls),
            )
        else:
            logger.info(
                "PublishingAgent publish_item title=%r photos=%d",
                title[:80],
                len(picture_urls),
            )

        try:
            fb_response = self.facebook.post_content(
                title=title,
                description=description,
                picture_url=picture_url,
                picture_urls=picture_urls,
                hashtags=hashtags,
                scheduled_publish_time=scheduled_unix,
            )
            facebook_post_id = fb_response.get("id")
            is_scheduled = scheduled_publish_at is not None or fb_response.get("scheduled")
            result = {
                "status": "scheduled" if is_scheduled else "published",
                "title": title,
                "picture_url": picture_url,
                "picture_urls": picture_urls,
                "category": category,
                "hashtags": hashtags,
                "photo_count": fb_response.get("photo_count", len(picture_urls)),
                "id": facebook_post_id,
                "facebook_response": fb_response,
            }
            if scheduled_publish_at:
                result["scheduled_publish_at"] = scheduled_publish_at.isoformat()
                result["scheduled_publish_at_us"] = format_schedule_slot(scheduled_publish_at)
                result["scheduled_publish_time"] = scheduled_unix
            if facebook_post_id:
                trace = self._trace_post(
                    facebook_post_id=facebook_post_id,
                    title=title,
                    description=description,
                    picture_url=picture_url,
                    picture_urls=picture_urls,
                    category=category,
                    hashtags=hashtags,
                    content_batch_id=content_batch_id,
                    publish_batch_id=publish_batch_id,
                    scheduled_publish_at=scheduled_publish_at,
                )
                if trace:
                    result["supabase_id"] = trace.get("id")
            return result
        except FacebookConnectorError as exc:
            logger.warning("PublishingAgent failed title=%r error=%s", title[:80], exc)
            return {
                "status": "failed",
                "title": title,
                "picture_url": picture_url,
                "picture_urls": picture_urls,
                "category": category,
                "error": str(exc),
            }

    def delete_post(self, facebook_post_id: str) -> dict[str, Any]:
        logger.info("PublishingAgent delete_post id=%s", facebook_post_id)
        fb_response = self.facebook.delete_post(facebook_post_id)

        trace = None
        if self.posts_repo:
            try:
                trace = self.posts_repo.mark_deleted(facebook_post_id)
            except Exception as exc:
                logger.warning("Failed to mark deleted in Supabase id=%s error=%s", facebook_post_id, exc)

        return {
            "facebook_post_id": facebook_post_id,
            "facebook_response": fb_response,
            "supabase": trace,
        }

    def _save_publish_log(self, batch_id: str, results: list[dict[str, Any]]) -> dict[str, Any]:
        publish_batch_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        batch_dir = TEMP_PUBLISHED_DIR / publish_batch_id
        batch_dir.mkdir(parents=True, exist_ok=True)

        published_count = sum(1 for r in results if r.get("status") == "published")
        scheduled_count = sum(1 for r in results if r.get("status") == "scheduled")
        manifest = {
            "publish_batch_id": publish_batch_id,
            "source_batch_id": batch_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "schedule_timezone": str(get_schedule_timezone()),
            "total": len(results),
            "published": published_count,
            "scheduled": scheduled_count,
            "failed": len(results) - published_count - scheduled_count,
            "results": results,
        }
        manifest_path = batch_dir / "publish_manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        logger.info(
            "PublishingAgent saved log batch=%s published=%d scheduled=%d/%d",
            publish_batch_id,
            published_count,
            scheduled_count,
            len(results),
        )
        return {
            "publish_batch_id": publish_batch_id,
            "saved_dir": str(batch_dir),
            "manifest_path": str(manifest_path),
            "total": len(results),
            "published": published_count,
            "scheduled": scheduled_count,
            "failed": len(results) - published_count - scheduled_count,
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
        *,
        schedule: bool = False,
    ) -> dict[str, Any]:
        logger.info("PublishingAgent publish_items count=%d schedule=%s", len(items), schedule)
        publish_batch_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        schedule_times = compute_schedule_times(len(items)) if schedule else []

        results = [
            self.publish_item(
                item,
                content_batch_id=source_batch_id,
                publish_batch_id=publish_batch_id,
                scheduled_publish_at=schedule_times[index] if schedule else None,
            )
            for index, item in enumerate(items)
        ]
        saved = self._save_publish_log(source_batch_id or "inline", results)
        saved["publish_batch_id"] = publish_batch_id
        saved["scheduled"] = schedule
        if schedule_times:
            saved["schedule_timezone"] = str(get_schedule_timezone())
            saved["schedule_slots"] = [
                {
                    "index": index,
                    "scheduled_publish_at": slot.isoformat(),
                    "scheduled_publish_at_us": format_schedule_slot(slot),
                }
                for index, slot in enumerate(schedule_times)
            ]
        return saved

    def publish_batch(
        self,
        batch_id: str,
        *,
        schedule: bool = False,
    ) -> dict[str, Any]:
        logger.info("PublishingAgent publish_batch batch_id=%s schedule=%s", batch_id, schedule)
        source_batch_id, items = self._load_items_from_batch(batch_id)
        return self.publish_items(items, source_batch_id=source_batch_id, schedule=schedule)

    def list_traced_posts(self, limit: int = 50, status: str | None = None) -> list[dict[str, Any]]:
        if not self.posts_repo:
            return []
        return self.posts_repo.list_posts(limit=limit, status=status)
