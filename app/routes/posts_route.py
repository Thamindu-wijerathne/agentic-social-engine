import logging

from fastapi import APIRouter, HTTPException, Query

from app.agents.publishing_agent import PublishingAgent
from app.connectors.fb_connector import FacebookConnectorError
from app.connectors.supabase_connector import SupabaseConnectorError, get_supabase_connector
from app.repositories.published_posts_repository import (
    PublishedPostsRepositoryError,
    get_published_posts_repository,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/posts", tags=["posts"])


@router.get("/published")
def list_published_posts(
    limit: int = Query(default=50, ge=1, le=200),
    status: str | None = Query(default=None, description="published | failed | deleted"),
):
    """List traced Facebook posts from Supabase."""
    repo = get_published_posts_repository()
    if not get_supabase_connector() or not repo:
        raise HTTPException(status_code=503, detail="Supabase is not configured")

    logger.info("/posts/published limit=%d status=%s", limit, status)
    posts = repo.list_posts(limit=limit, status=status)
    return {"count": len(posts), "items": posts}


@router.get("/published/{facebook_post_id}")
def get_published_post(facebook_post_id: str):
    """Get one traced post by Facebook post id."""
    repo = get_published_posts_repository()
    if not get_supabase_connector() or not repo:
        raise HTTPException(status_code=503, detail="Supabase is not configured")

    post = repo.get_by_facebook_post_id(facebook_post_id)
    if not post:
        raise HTTPException(status_code=404, detail=f"Post not found: {facebook_post_id}")
    return post


@router.delete("/published/{facebook_post_id}")
def delete_published_post(facebook_post_id: str, dry_run: bool = Query(default=False)):
    """Delete a Facebook post and mark it deleted in Supabase."""
    logger.info("/posts/published delete id=%s dry_run=%s", facebook_post_id, dry_run)
    try:
        publisher = PublishingAgent(dry_run=dry_run)
        result = publisher.delete_post(facebook_post_id)
    except FacebookConnectorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (PublishedPostsRepositoryError, SupabaseConnectorError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return result
