import logging
from typing import Any

import requests

from config.settings import settings

logger = logging.getLogger(__name__)

GRAPH_API_VERSION = "v21.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"


class FacebookConnectorError(Exception):
    pass


class FacebookConnector:
    """Post content to a Facebook Page via the Graph API."""

    def __init__(
        self,
        access_token: str | None = None,
        page_id: str | None = None,
    ):
        self.access_token = access_token or settings.facebook_access_token
        self.page_id = page_id or settings.facebook_page_id

        if not self.access_token:
            raise FacebookConnectorError("facebook_access_token is not configured")
        if not self.page_id:
            raise FacebookConnectorError("facebook_page_id is not configured")

    def _post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
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
            raise FacebookConnectorError(f"Facebook API error: {message}")

        logger.info("Facebook post complete post_id=%s", body.get("id"))
        return body

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
