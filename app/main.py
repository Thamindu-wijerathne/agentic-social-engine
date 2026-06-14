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

app = FastAPI()

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


@app.get("/")
def read_root():
    return {"message": "api is running"}
