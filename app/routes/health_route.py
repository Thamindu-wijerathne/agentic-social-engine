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


@router.get(
    "",
    summary="Liveness check",
    description="Returns 200 if the API process is up. Does not check external dependencies.",
)
@router.get(
    "/",
    summary="Liveness check",
    description="Returns 200 if the API process is up. Does not check external dependencies.",
    include_in_schema=False,
)
def health_live():
    return {"status": "ok", "service": "agentic-social-engine"}


@router.get(
    "/ready",
    summary="Readiness check",
    description=(
        "Checks core pipeline dependencies: LLM config, prompts, agents, temp dirs, and at least one news tool.\n\n"
        "Returns 503 if the pipeline cannot run."
    ),
)
def health_ready(response: Response):
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


@router.get(
    "/status",
    summary="Full health report",
    description="Detailed health report grouped by agents, tools, connectors, and pipeline storage.",
)
def health_status(response: Response):
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


@router.get(
    "/agents",
    summary="Agent health",
    description="Health checks for LLM agents, system prompts, and agent graph initialization.",
)
def health_agents(response: Response):
    payload = summarize_checks(run_agent_health_checks())
    response.status_code = _response_status_code(payload["status"])
    return payload


@router.get(
    "/tools",
    summary="News tool health",
    description="Connectivity checks for GNews, Google News RSS, and the animal news scraper source.",
)
def health_tools(response: Response):
    payload = summarize_checks(run_tool_health_checks())
    response.status_code = _response_status_code(payload["status"])
    return payload


@router.get(
    "/connectors",
    summary="Connector health",
    description="Validates Facebook page token and Supabase database reachability.",
)
def health_connectors(response: Response):
    payload = summarize_checks(run_connector_health_checks())
    response.status_code = _response_status_code(payload["status"])
    return payload


@router.get(
    "/pipeline",
    summary="Pipeline path health",
    description="Checks agents, writable temp directories, and trend/news tools required for the content pipeline.",
)
def health_pipeline(response: Response):
    payload = summarize_checks(run_pipeline_health_checks())
    response.status_code = _response_status_code(payload["status"])
    return payload
