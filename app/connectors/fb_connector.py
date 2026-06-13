import json
import logging
import uuid
from typing import Any

import requests

from config.settings import settings

logger = logging.getLogger(__name__)

GRAPH_API_VERSION = "v21.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"
MOCK_FB_PAGE_ID = "926705803858447"


def _mock_facebook_post_id() -> str:
    """Unique id per dry-run post (real FB ids are also unique per post)."""
    return f"{MOCK_FB_PAGE_ID}_{uuid.uuid4().hex[:18]}"


class FacebookConnectorError(Exception):
    pass


class FacebookConnector:
    """Post content to a Facebook Page via the Graph API."""

    def __init__(
        self,
        access_token: str | None = None,
        page_id: str | None = None,
        dry_run: bool = False,
    ):
        self.dry_run = dry_run
        self.access_token = access_token or settings.facebook_access_token
        self.page_id = page_id or settings.facebook_page_id

        if not self.dry_run:
            if not self.access_token:
                raise FacebookConnectorError("facebook_access_token is not configured")
            if not self.page_id:
                raise FacebookConnectorError("facebook_page_id is not configured")

    def _post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self.dry_run:
            post_id = _mock_facebook_post_id()
            logger.info("Facebook dry_run post endpoint=%s id=%s", endpoint, post_id)
            return {"id": post_id}

        url = f"{GRAPH_API_BASE}/{self.page_id}/{endpoint}"
        data = {**payload, "access_token": self.access_token}

        logger.info("Facebook post start endpoint=%s page_id=%s", endpoint, self.page_id)
        try:
            response = requests.post(url, data=data, timeout=30)
            body = response.json()
        except requests.RequestException as exc:
            logger.warning("Facebook post request failed: %s", exc)
            raise FacebookConnectorError(f"Facebook request failed: {exc}") from exc

        if not response.ok:
            error = body.get("error", {}) if isinstance(body, dict) else {}
            message = error.get("message", response.text)
            logger.warning("Facebook post rejected: %s", message)
            if "publish_actions" in message.lower():
                raise FacebookConnectorError(
                    "Facebook rejected the token: use a Page Access Token with pages_manage_posts, "
                    "not a User token. In Graph API Explorer: GET /me/accounts and copy the page "
                    "access_token for your page into facebook_access_token in .env"
                )
            raise FacebookConnectorError(f"Facebook API error: {message}")

        logger.info("Facebook post complete post_id=%s", body.get("id"))
        return body

    def delete_post(self, post_id: str) -> dict[str, Any]:
        """Delete a Facebook post by Graph API post id."""
        if self.dry_run:
            logger.info("Facebook dry_run delete post_id=%s", post_id)
            return {"success": True}

        if not post_id.strip():
            raise FacebookConnectorError("post_id cannot be empty")

        url = f"{GRAPH_API_BASE}/{post_id.strip()}"
        logger.info("Facebook delete start post_id=%s", post_id)
        try:
            response = requests.delete(
                url,
                params={"access_token": self.access_token},
                timeout=30,
            )
            body = response.json() if response.content else {}
        except requests.RequestException as exc:
            logger.warning("Facebook delete request failed: %s", exc)
            raise FacebookConnectorError(f"Facebook delete failed: {exc}") from exc

        if not response.ok:
            error = body.get("error", {}) if isinstance(body, dict) else {}
            message = error.get("message", response.text)
            logger.warning("Facebook delete rejected: %s", message)
            raise FacebookConnectorError(f"Facebook API error: {message}")

        logger.info("Facebook delete complete post_id=%s", post_id)
        return body if body else {"success": True}

    def post_message(self, message: str) -> dict[str, Any]:
        """Publish a text-only post to the configured Facebook Page."""
        if not message.strip():
            raise FacebookConnectorError("message cannot be empty")
        return self._post("feed", {"message": message})

    def post_link(self, message: str, link: str) -> dict[str, Any]:
        """Publish a post with a link preview."""
        if not link.strip():
            raise FacebookConnectorError("link cannot be empty")
        return self._post("feed", {"message": message, "link": link})

    def post_photo(
        self,
        message: str,
        image_url: str,
        *,
        scheduled_publish_time: int | None = None,
    ) -> dict[str, Any]:
        """Publish a post with a photo from a public image URL."""
        if not image_url.strip():
            raise FacebookConnectorError("image_url cannot be empty")
        if scheduled_publish_time:
            return self._post_scheduled_content(message, [image_url.strip()], scheduled_publish_time)
        return self._post("photos", {"caption": message, "url": image_url})

    def _upload_unpublished_photos(self, image_urls: list[str]) -> list[str]:
        media_ids: list[str] = []
        for index, url in enumerate(image_urls):
            body = self._post("photos", {"url": url, "published": "false"})
            photo_id = body.get("id")
            if not photo_id:
                raise FacebookConnectorError(f"Failed to upload unpublished photo #{index + 1}")
            media_ids.append(str(photo_id))
        return media_ids

    def _post_scheduled_content(
        self,
        message: str,
        image_urls: list[str],
        scheduled_publish_time: int,
    ) -> dict[str, Any]:
        urls = [url.strip() for url in image_urls if url and str(url).strip()]
        if not urls:
            raise FacebookConnectorError("image_urls cannot be empty")

        if self.dry_run:
            post_id = _mock_facebook_post_id()
            logger.info(
                "Facebook dry_run scheduled count=%d id=%s time=%s",
                len(urls),
                post_id,
                scheduled_publish_time,
            )
            return {
                "id": post_id,
                "photo_count": len(urls),
                "scheduled_publish_time": scheduled_publish_time,
                "scheduled": True,
            }

        media_ids = self._upload_unpublished_photos(urls)
        payload: dict[str, Any] = {
            "message": message,
            "published": "false",
            "scheduled_publish_time": str(scheduled_publish_time),
            "unpublished_content_type": "SCHEDULED",
        }
        for index, photo_id in enumerate(media_ids):
            payload[f"attached_media[{index}]"] = json.dumps({"media_fbid": photo_id})

        result = self._post("feed", payload)
        result["photo_count"] = len(media_ids)
        result["photo_ids"] = media_ids
        result["scheduled_publish_time"] = scheduled_publish_time
        result["scheduled"] = True
        return result

    def post_multi_photo(
        self,
        message: str,
        image_urls: list[str],
        *,
        scheduled_publish_time: int | None = None,
    ) -> dict[str, Any]:
        """Publish one feed post with multiple photos from public URLs."""
        urls = [url.strip() for url in image_urls if url and str(url).strip()]
        if not urls:
            raise FacebookConnectorError("image_urls cannot be empty")

        if scheduled_publish_time:
            return self._post_scheduled_content(message, urls, scheduled_publish_time)

        if self.dry_run:
            post_id = _mock_facebook_post_id()
            logger.info("Facebook dry_run multi_photo count=%d id=%s", len(urls), post_id)
            return {"id": post_id, "photo_count": len(urls)}

        media_ids = self._upload_unpublished_photos(urls)
        payload: dict[str, Any] = {"message": message}
        for index, photo_id in enumerate(media_ids):
            payload[f"attached_media[{index}]"] = json.dumps({"media_fbid": photo_id})

        result = self._post("feed", payload)
        result["photo_count"] = len(media_ids)
        result["photo_ids"] = media_ids
        return result

    def post_content(
        self,
        title: str,
        description: str,
        picture_url: str | None = None,
        picture_urls: list[str] | None = None,
        hashtags: list[str] | None = None,
        scheduled_publish_time: int | None = None,
    ) -> dict[str, Any]:
        """Publish content-writer output with one or more photos."""
        urls: list[str] = []
        seen: set[str] = set()
        for candidate in picture_urls or []:
            url = str(candidate).strip()
            if url and url not in seen:
                seen.add(url)
                urls.append(url)

        primary = str(picture_url or "").strip()
        if primary and primary not in seen:
            urls.insert(0, primary)

        if not urls:
            raise FacebookConnectorError("picture_url is required for Facebook posts")

        parts = [title.strip()]
        if description.strip():
            parts.append(description.strip())
        if hashtags:
            tag_line = " ".join(
                tag if tag.startswith("#") else f"#{tag.lstrip('#')}"
                for tag in hashtags
                if str(tag).strip()
            )
            if tag_line:
                parts.append(tag_line)
        message = "\n\n".join(parts)

        if scheduled_publish_time:
            return self._post_scheduled_content(message, urls, scheduled_publish_time)

        if len(urls) == 1:
            return self.post_photo(message, urls[0])
        return self.post_multi_photo(message, urls)

    def post_article(
        self,
        topic: str,
        description: str,
        context: str,
        img_urls: list[str] | None = None,
        link: str | None = None,
    ) -> dict[str, Any]:
        """Publish research-style content (topic, description, context, optional image/link)."""
        parts = [topic.strip()]
        if description.strip():
            parts.append(description.strip())
        if context.strip():
            parts.append(context.strip())
        message = "\n\n".join(parts)

        if img_urls:
            return self.post_photo(message, img_urls[0])
        if link:
            return self.post_link(message, link)
        return self.post_message(message)
