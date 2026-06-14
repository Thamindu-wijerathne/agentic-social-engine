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
        description="Content writer items. Each needs at least title, description, and picture_url (or picture_urls).",
    )


class PublishBatchRequest(BaseModel):
    batch_id: str = Field(
        ...,
        description="Content batch id from `temp/content/{batch_id}/manifest.json`.",
        examples=["20260611_104934"],
    )


@router.post(
    "/items",
    summary="Publish content items",
    description=(
        "Publish a list of content-writer items to Facebook immediately (not scheduled unless items "
        "were pre-built for scheduling elsewhere).\n\n"
        "Set `dry_run=true` to return mock Facebook IDs without calling the Graph API."
    ),
)
def publish_items(
    body: PublishItemsRequest,
    dry_run: bool = Query(default=False, description="Mock publish without calling Facebook API"),
):
    logger.info("/publish/items start count=%d dry_run=%s", len(body.items), dry_run)
    try:
        publisher = PublishingAgent(dry_run=dry_run)
        result = publisher.publish_items(body.items)
    except (FacebookConnectorError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    logger.info("/publish/items done published=%d", result.get("published", 0))
    return result


@router.post(
    "/batch",
    summary="Publish saved content batch",
    description=(
        "Load all items from a saved content batch folder and publish them to Facebook.\n\n"
        "Set `dry_run=true` to simulate publish without real API calls."
    ),
)
def publish_batch(
    body: PublishBatchRequest,
    dry_run: bool = Query(default=False, description="Mock publish without calling Facebook API"),
):
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


@router.delete(
    "/{facebook_post_id}",
    summary="Delete Facebook post",
    description=(
        "Delete a post on Facebook by Graph API post id and mark it `deleted` in Supabase when tracing is enabled.\n\n"
        "This is the only delete endpoint — `/posts` is read-only history."
    ),
)
def delete_post(
    facebook_post_id: str,
    dry_run: bool = Query(default=False, description="Mock delete without calling Facebook API"),
):
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
