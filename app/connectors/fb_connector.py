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

    def post_photo(self, message: str, image_url: str) -> dict[str, Any]:
        """Publish a post with a photo from a public image URL."""
        if not image_url.strip():
            raise FacebookConnectorError("image_url cannot be empty")
        return self._post("photos", {"caption": message, "url": image_url})

    def post_content(
        self,
        title: str,
        description: str,
        picture_url: str | None = None,
    ) -> dict[str, Any]:
        """Publish content-writer output (title, description, required picture)."""
        if not picture_url or not picture_url.strip():
            raise FacebookConnectorError("picture_url is required for Facebook posts")

        parts = [title.strip()]
        if description.strip():
            parts.append(description.strip())
        message = "\n\n".join(parts)
        return self.post_photo(message, picture_url.strip())

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
