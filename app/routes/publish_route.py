import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.agents.publishing_agent import PublishingAgent
from app.connectors.fb_connector import FacebookConnectorError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/publish", tags=["publish"])


class PublishItemsRequest(BaseModel):
    items: list[dict[str, Any]] = Field(
        ...,
        description="Content writer items with title, description, picture_url",
    )


class PublishBatchRequest(BaseModel):
    batch_id: str = Field(
        ...,
        description="Content batch id from temp/content/{batch_id}",
        examples=["20260611_104934"],
    )


@router.post("/items")
def publish_items(
    body: PublishItemsRequest,
    dry_run: bool = Query(default=False, description="Mock publish without calling Facebook API"),
):
    """Publish a list of content items to Facebook."""
    logger.info("/publish/items start count=%d dry_run=%s", len(body.items), dry_run)
    try:
        publisher = PublishingAgent(dry_run=dry_run)
        result = publisher.publish_items(body.items)
    except (FacebookConnectorError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    logger.info("/publish/items done published=%d", result.get("published", 0))
    return result


@router.post("/batch")
def publish_batch(
    body: PublishBatchRequest,
    dry_run: bool = Query(default=False, description="Mock publish without calling Facebook API"),
):
    """Publish all items from a saved content batch folder."""
    logger.info("/publish/batch start batch_id=%s dry_run=%s", body.batch_id, dry_run)
    try:
        publisher = PublishingAgent(dry_run=dry_run)
        result = publisher.publish_batch(body.batch_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (FacebookConnectorError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    logger.info("/publish/batch done published=%d", result.get("published", 0))
    return result


@router.delete("/{facebook_post_id}")
def delete_post(
    facebook_post_id: str,
    dry_run: bool = Query(default=False, description="Mock delete without calling Facebook API"),
):
    """Delete a Facebook post by Graph API post id."""
    post_id = facebook_post_id.strip()
    if not post_id:
        raise HTTPException(status_code=400, detail="facebook_post_id is required")

    logger.info("/publish/delete start id=%s dry_run=%s", post_id, dry_run)
    try:
        publisher = PublishingAgent(dry_run=dry_run)
        result = publisher.delete_post(post_id)
    except FacebookConnectorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    logger.info("/publish/delete done id=%s", post_id)
    return result
