import logging
import time

from fastapi import FastAPI, Request

from app.routes.health_route import router as health_router
from app.routes.pipeline_route import router as pipeline_router
from app.routes.posts_route import router as posts_router
from app.routes.publish_route import router as publish_router
from app.routes.scraper_route import router as scraper_router
from app.routes.test_route import router as test_router
from app.routes.usage_route import router as usage_router
from config.log_config import configure_logging

configure_logging()
logger = logging.getLogger(__name__)

OPENAPI_TAGS = [
    {
        "name": "health",
        "description": "Liveness, readiness, and dependency health checks for agents, tools, and connectors.",
    },
    {
        "name": "pipeline",
        "description": "Production content pipeline: trend → research → content writer → optional Facebook publish.",
    },
    {
        "name": "publish",
        "description": "Facebook publish actions: post items or batches, delete posts. Use `dry_run=true` to mock API calls.",
    },
    {
        "name": "posts",
        "description": "Read-only history of published posts stored in Supabase (audit/trace). Delete via `/publish`.",
    },
    {
        "name": "usage",
        "description": "Token usage and estimated LLM cost logs saved after pipeline runs.",
    },
    {
        "name": "test",
        "description": "Dev endpoints to run individual agents or the full pipeline with safe defaults.",
    },
    {
        "name": "scraper",
        "description": "Standalone web scrape and listing crawl utilities.",
    },
]

app = FastAPI(
    title="Agentic Social Engine",
    description=(
        "API for an agentic social content workflow: discover US news trends, research topics, "
        "write Facebook-ready posts, publish or schedule them, and trace results in Supabase."
    ),
    version="1.0.0",
    openapi_tags=OPENAPI_TAGS,
)

app.include_router(health_router)
app.include_router(test_router)
app.include_router(pipeline_router)
app.include_router(publish_router)
app.include_router(posts_router)
app.include_router(usage_router)
app.include_router(scraper_router)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    logger.info("→ %s %s", request.method, request.url.path)
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "← %s %s status=%s %.0fms",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response


@app.get(
    "/",
    summary="API root",
    description="Simple liveness check that the API process is running.",
)
def read_root():
    return {"message": "api is running"}
