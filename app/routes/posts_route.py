import logging

from fastapi import APIRouter, HTTPException, Query

from app.connectors.supabase_connector import SupabaseConnectorError, get_supabase_connector
from app.repositories.published_posts_repository import get_published_posts_repository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/posts", tags=["posts"])


@router.get(
    "/published",
    summary="List published posts",
    description=(
        "List Facebook posts traced in Supabase after publish/schedule runs.\n\n"
        "Requires Supabase. To delete a post, use `DELETE /publish/{facebook_post_id}`."
    ),
)
def list_published_posts(
    limit: int = Query(default=50, ge=1, le=200, description="Max rows to return"),
    status: str | None = Query(
        default=None,
        description="Filter by status: published, scheduled, failed, or deleted",
    ),
):
    repo = get_published_posts_repository()
    if not get_supabase_connector() or not repo:
        raise HTTPException(status_code=503, detail="Supabase is not configured")

    logger.info("/posts/published limit=%d status=%s", limit, status)
    try:
        posts = repo.list_posts(limit=limit, status=status)
    except SupabaseConnectorError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"count": len(posts), "items": posts}


@router.get(
    "/published/{facebook_post_id}",
    summary="Get published post",
    description="Fetch one traced post record by Facebook post id from Supabase.",
)
def get_published_post(
    facebook_post_id: str,
):
    repo = get_published_posts_repository()
    if not get_supabase_connector() or not repo:
        raise HTTPException(status_code=503, detail="Supabase is not configured")

    try:
        post = repo.get_by_facebook_post_id(facebook_post_id)
    except SupabaseConnectorError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not post:
        raise HTTPException(status_code=404, detail=f"Post not found: {facebook_post_id}")
    return post
