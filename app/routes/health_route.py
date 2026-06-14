import logging

from fastapi import APIRouter, Response

from app.health.checks import (
    aggregate_status,
    run_agent_health_checks,
    run_connector_health_checks,
    run_pipeline_health_checks,
    run_readiness_checks,
    run_tool_health_checks,
    summarize_checks,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/health", tags=["health"])


def _response_status_code(status: str) -> int:
    return 200 if status in ("ok", "degraded") else 503


@router.get("")
@router.get("/")
def health_live():
    """Liveness probe — API process is running."""
    return {"status": "ok", "service": "agentic-social-engine"}


@router.get("/ready")
def health_ready(response: Response):
    """Readiness probe — core pipeline dependencies are available."""
    checks = run_readiness_checks()
    payload = summarize_checks(checks)
    response.status_code = _response_status_code(payload["status"])
    logger.info(
        "/health/ready status=%s ok=%d degraded=%d fail=%d",
        payload["status"],
        payload["summary"]["ok"],
        payload["summary"]["degraded"],
        payload["summary"]["fail"],
    )
    return payload


@router.get("/status")
def health_status(response: Response):
    """Full health report for agents, tools, connectors, and pipeline storage."""
    agent_checks = run_agent_health_checks()
    tool_checks = run_tool_health_checks()
    connector_checks = run_connector_health_checks()
    pipeline_checks = run_pipeline_health_checks()

    sections = {
        "agents": summarize_checks(agent_checks),
        "tools": summarize_checks(tool_checks),
        "connectors": summarize_checks(connector_checks),
        "pipeline": summarize_checks(pipeline_checks),
    }
    all_checks = agent_checks + tool_checks + connector_checks
    overall_status = aggregate_status(all_checks)
    payload = {
        "status": overall_status,
        "sections": sections,
    }
    response.status_code = _response_status_code(overall_status)
    return payload


@router.get("/agents")
def health_agents(response: Response):
    """Health checks for LLM agents and prompts."""
    payload = summarize_checks(run_agent_health_checks())
    response.status_code = _response_status_code(payload["status"])
    return payload


@router.get("/tools")
def health_tools(response: Response):
    """Health checks for trend/news tools."""
    payload = summarize_checks(run_tool_health_checks())
    response.status_code = _response_status_code(payload["status"])
    return payload


@router.get("/connectors")
def health_connectors(response: Response):
    """Health checks for Facebook and Supabase connectors."""
    payload = summarize_checks(run_connector_health_checks())
    response.status_code = _response_status_code(payload["status"])
    return payload


@router.get("/pipeline")
def health_pipeline(response: Response):
    """Health checks for the full content pipeline path."""
    payload = summarize_checks(run_pipeline_health_checks())
    response.status_code = _response_status_code(payload["status"])
    return payload
