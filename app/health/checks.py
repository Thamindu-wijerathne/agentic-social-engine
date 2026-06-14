import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

import requests

from app.agents.content_writer_agent import TEMP_CONTENT_DIR, ContentWriterAgent
from app.agents.publishing_agent import TEMP_PUBLISHED_DIR, PublishingAgent
from app.agents.research_agent import ResearchAgent
from app.agents.trend_agent import TrendAgent
from app.connectors.fb_connector import GRAPH_API_BASE
from app.connectors.supabase_connector import SupabaseConnectorError, get_supabase_connector
from app.prompts.PromptManager import PromptManager
from app.tools.trend_agent.animal_news_scraper_tool import GOOD_GOOD_GOOD_ANIMALS_URL
from app.tools.trend_agent.googlenews_tool import GOOGLE_NEWS_RSS_URL, _BROWSER_HEADERS
from config.settings import settings

logger = logging.getLogger(__name__)

AGENT_PROMPTS: dict[str, str] = {
    "trend": "trend_agent_system_prompt",
    "research": "research_agent_system_prompt",
    "content_writer": "content_writer_agent_system_prompt",
}

TOOL_HTTP_TIMEOUT = 10


@dataclass
class HealthCheckResult:
    name: str
    status: str
    message: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    latency_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _run_check(name: str, fn: Callable[[], HealthCheckResult]) -> HealthCheckResult:
    start = time.perf_counter()
    try:
        result = fn()
    except Exception as exc:
        logger.warning("Health check %s raised: %s", name, exc)
        result = HealthCheckResult(name=name, status="fail", message=str(exc))
    result.latency_ms = round((time.perf_counter() - start) * 1000, 1)
    return result


def aggregate_status(checks: list[HealthCheckResult]) -> str:
    if any(check.status == "fail" for check in checks):
        return "fail"
    if any(check.status == "degraded" for check in checks):
        return "degraded"
    return "ok"


def summarize_checks(checks: list[HealthCheckResult]) -> dict[str, Any]:
    status = aggregate_status(checks)
    return {
        "status": status,
        "summary": {
            "total": len(checks),
            "ok": sum(1 for check in checks if check.status == "ok"),
            "degraded": sum(1 for check in checks if check.status == "degraded"),
            "fail": sum(1 for check in checks if check.status == "fail"),
        },
        "checks": [check.to_dict() for check in checks],
    }


def check_llm_config() -> HealthCheckResult:
    missing = []
    if not settings.CLAUDE_API_KEY:
        missing.append("CLAUDE_API_KEY")
    if not settings.CLAUDE_MODEL:
        missing.append("CLAUDE_MODEL")
    if missing:
        return HealthCheckResult(
            name="llm_config",
            status="fail",
            message=f"Missing config: {', '.join(missing)}",
        )
    return HealthCheckResult(
        name="llm_config",
        status="ok",
        message="Claude config present",
        details={"model": settings.CLAUDE_MODEL, "fast_model": settings.CLAUDE_MODEL_FAST},
    )


def check_prompts() -> HealthCheckResult:
    loaded: dict[str, int] = {}
    for agent, prompt_name in AGENT_PROMPTS.items():
        text = PromptManager.get("agent_prompts", prompt_name)
        loaded[agent] = len(text)

    return HealthCheckResult(
        name="prompts",
        status="ok",
        message="Agent prompts loaded",
        details={"prompt_chars": loaded},
    )


def _check_agent_init(name: str, factory: Callable[[], Any]) -> HealthCheckResult:
    agent = factory()
    has_agent_graph = hasattr(agent, "agent")
    return HealthCheckResult(
        name=f"agent_{name}",
        status="ok",
        message=f"{name} agent initialized",
        details={
            "has_agent_graph": has_agent_graph,
            "llm_configured": getattr(agent, "llm", None) is not None,
        },
    )


def check_trend_agent() -> HealthCheckResult:
    return _check_agent_init("trend", TrendAgent)


def check_research_agent() -> HealthCheckResult:
    return _check_agent_init("research", ResearchAgent)


def check_content_writer_agent() -> HealthCheckResult:
    return _check_agent_init("content_writer", ContentWriterAgent)


def check_publishing_agent() -> HealthCheckResult:
    agent = PublishingAgent(dry_run=True)
    facebook_ready = bool(agent.facebook.access_token and agent.facebook.page_id)
    return HealthCheckResult(
        name="agent_publishing",
        status="ok" if agent.dry_run else "degraded",
        message="Publishing agent initialized (dry-run)",
        details={
            "dry_run": agent.dry_run,
            "facebook_configured": facebook_ready,
            "supabase_tracing": agent.posts_repo is not None,
        },
    )


def check_temp_directories() -> HealthCheckResult:
    directories = {
        "content": TEMP_CONTENT_DIR,
        "published": TEMP_PUBLISHED_DIR,
    }
    details: dict[str, Any] = {}
    for label, path in directories.items():
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".health_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        details[label] = {"path": str(path), "writable": True}

    return HealthCheckResult(
        name="temp_directories",
        status="ok",
        message="Pipeline temp directories are writable",
        details=details,
    )


def check_gnews_tool() -> HealthCheckResult:
    if not settings.GNEWS_API_KEY:
        return HealthCheckResult(
            name="tool_gnews",
            status="fail",
            message="GNEWS_API_KEY is not configured",
        )

    response = requests.get(
        "https://gnews.io/api/v4/top-headlines",
        params={
            "category": "health",
            "lang": "en",
            "country": "us",
            "max": 1,
            "apikey": settings.GNEWS_API_KEY,
        },
        timeout=TOOL_HTTP_TIMEOUT,
    )

    if response.status_code == 429:
        return HealthCheckResult(
            name="tool_gnews",
            status="degraded",
            message="GNews rate limited",
            details={"http_status": response.status_code},
        )

    if not response.ok:
        return HealthCheckResult(
            name="tool_gnews",
            status="fail",
            message=f"GNews request failed with status {response.status_code}",
            details={"http_status": response.status_code},
        )

    payload = response.json()
    article_count = len(payload.get("articles", []))
    return HealthCheckResult(
        name="tool_gnews",
        status="ok",
        message="GNews API reachable",
        details={"http_status": response.status_code, "sample_articles": article_count},
    )


def check_googlenews_tool() -> HealthCheckResult:
    response = requests.get(
        GOOGLE_NEWS_RSS_URL,
        headers=_BROWSER_HEADERS,
        timeout=TOOL_HTTP_TIMEOUT,
    )
    if not response.ok:
        return HealthCheckResult(
            name="tool_googlenews",
            status="degraded",
            message=f"Google News RSS returned status {response.status_code}",
            details={"http_status": response.status_code},
        )

    return HealthCheckResult(
        name="tool_googlenews",
        status="ok",
        message="Google News RSS reachable",
        details={"http_status": response.status_code, "bytes": len(response.content)},
    )


def check_animal_scraper_tool() -> HealthCheckResult:
    response = requests.get(
        GOOD_GOOD_GOOD_ANIMALS_URL,
        headers=_BROWSER_HEADERS,
        timeout=TOOL_HTTP_TIMEOUT,
    )
    if not response.ok:
        return HealthCheckResult(
            name="tool_animal_scraper",
            status="fail",
            message=f"Animal news source returned status {response.status_code}",
            details={"url": GOOD_GOOD_GOOD_ANIMALS_URL, "http_status": response.status_code},
        )

    return HealthCheckResult(
        name="tool_animal_scraper",
        status="ok",
        message="Animal news source reachable",
        details={"url": GOOD_GOOD_GOOD_ANIMALS_URL, "http_status": response.status_code},
    )


def check_facebook_connector() -> HealthCheckResult:
    token = settings.facebook_access_token
    page_id = settings.facebook_page_id
    if not token or not page_id:
        return HealthCheckResult(
            name="connector_facebook",
            status="degraded",
            message="Facebook credentials not configured",
            details={"configured": False},
        )

    response = requests.get(
        f"{GRAPH_API_BASE}/{page_id}",
        params={"fields": "id,name", "access_token": token},
        timeout=TOOL_HTTP_TIMEOUT,
    )
    body = response.json() if response.content else {}
    if not response.ok:
        error = body.get("error", {}) if isinstance(body, dict) else {}
        return HealthCheckResult(
            name="connector_facebook",
            status="fail",
            message=error.get("message", f"Facebook API status {response.status_code}"),
            details={"http_status": response.status_code, "page_id": page_id},
        )

    return HealthCheckResult(
        name="connector_facebook",
        status="ok",
        message="Facebook page token is valid",
        details={
            "page_id": body.get("id", page_id),
            "page_name": body.get("name"),
        },
    )


def check_supabase_connector() -> HealthCheckResult:
    connector = get_supabase_connector()
    if not connector:
        return HealthCheckResult(
            name="connector_supabase",
            status="degraded",
            message="Supabase is not configured",
            details={"configured": False},
        )

    try:
        rows = connector.select("published_posts", limit=1)
    except SupabaseConnectorError as exc:
        return HealthCheckResult(
            name="connector_supabase",
            status="fail",
            message=str(exc),
            details={"configured": True},
        )

    return HealthCheckResult(
        name="connector_supabase",
        status="ok",
        message="Supabase reachable",
        details={"configured": True, "sample_rows": len(rows)},
    )


def run_agent_health_checks() -> list[HealthCheckResult]:
    checks = [
        ("llm_config", check_llm_config),
        ("prompts", check_prompts),
        ("trend_agent", check_trend_agent),
        ("research_agent", check_research_agent),
        ("content_writer_agent", check_content_writer_agent),
        ("publishing_agent", check_publishing_agent),
    ]
    return [_run_check(name, fn) for name, fn in checks]


def run_tool_health_checks() -> list[HealthCheckResult]:
    checks = [
        ("gnews", check_gnews_tool),
        ("googlenews", check_googlenews_tool),
        ("animal_scraper", check_animal_scraper_tool),
    ]
    return [_run_check(name, fn) for name, fn in checks]


def run_connector_health_checks() -> list[HealthCheckResult]:
    checks = [
        ("facebook", check_facebook_connector),
        ("supabase", check_supabase_connector),
    ]
    return [_run_check(name, fn) for name, fn in checks]


def run_pipeline_health_checks() -> list[HealthCheckResult]:
    checks = run_agent_health_checks()
    checks.append(_run_check("temp_directories", check_temp_directories))
    checks.extend(run_tool_health_checks())
    return checks


def run_readiness_checks() -> list[HealthCheckResult]:
    critical = [
        _run_check("llm_config", check_llm_config),
        _run_check("prompts", check_prompts),
        _run_check("trend_agent", check_trend_agent),
        _run_check("research_agent", check_research_agent),
        _run_check("content_writer_agent", check_content_writer_agent),
        _run_check("temp_directories", check_temp_directories),
    ]
    tool_checks = run_tool_health_checks()
    has_news_source = any(
        check.status in ("ok", "degraded") for check in tool_checks
    ) and not all(check.status == "fail" for check in tool_checks)
    if not has_news_source:
        critical.append(
            HealthCheckResult(
                name="news_sources",
                status="fail",
                message="No trend tools are reachable",
            )
        )
    else:
        critical.append(
            HealthCheckResult(
                name="news_sources",
                status="ok",
                message="At least one trend tool is reachable",
            )
        )
    return critical
