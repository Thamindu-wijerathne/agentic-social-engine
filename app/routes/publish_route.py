import logging
from typing import Any

from fastapi import APIRouter, HTTPException
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
def publish_items(body: PublishItemsRequest):
    """Publish a list of content items to Facebook."""
    logger.info("/publish/items start count=%d", len(body.items))
    try:
        publisher = PublishingAgent()
        result = publisher.publish_items(body.items)
    except (FacebookConnectorError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    logger.info("/publish/items done published=%d", result.get("published", 0))
    return result


@router.post("/batch")
def publish_batch(body: PublishBatchRequest):
    """Publish all items from a saved content batch folder."""
    logger.info("/publish/batch start batch_id=%s", body.batch_id)
    try:
        publisher = PublishingAgent()
        result = publisher.publish_batch(body.batch_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (FacebookConnectorError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    logger.info("/publish/batch done published=%d", result.get("published", 0))
    return result
