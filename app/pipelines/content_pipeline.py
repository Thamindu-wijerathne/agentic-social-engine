import logging
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from app.agents.content_writer_agent import ContentWriterAgent
from app.agents.publishing_agent import PublishingAgent
from app.agents.research_agent import ResearchAgent
from app.agents.trend_agent import TrendAgent
from app.connectors.fb_connector import FacebookConnectorError
from app.core.token_usage import PipelineTokenUsage, log_token_usage
from app.repositories.token_usage_repository import save_token_usage_log
from config.settings import settings

logger = logging.getLogger(__name__)

class PipelineRequest(BaseModel):
    trend_prompt: str | None = Field(
        default=None,
        description="Optional override for the trend agent input prompt",
    )
    publish: bool = Field(
        default=False,
        description="If true, publish content to Facebook after content writer step",
    )
    publish_dry_run: bool = Field(
        default=False,
        description="If true, mock Facebook publish (no real API call). Useful for testing.",
    )


DEFAULT_TREND_PROMPT = (
    "Build today's topic list for older US adults with exactly 5 items: "
    "2 politics/public-affairs, 1 health, and 2 animal stories. "
    "Use gnews_tool for politics and health, and animal_news_scraper_tool for animals."
)


@dataclass
class PipelineResult:
    pipeline: list[str]
    trends: list[dict[str, Any]]
    research: list[dict[str, Any]]
    content: dict[str, Any]
    publishing: dict[str, Any] | None = None
    publishing_error: str | None = None
    token_usage: dict[str, Any] | None = None
    token_usage_log_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "pipeline": self.pipeline,
            "trends": {"count": len(self.trends), "items": self.trends},
            "research": {"count": len(self.research), "items": self.research},
            "content": self.content,
        }
        if self.publishing is not None:
            result["publishing"] = self.publishing
        if self.publishing_error:
            result["publishing_error"] = self.publishing_error
        if self.token_usage is not None:
            result["token_usage"] = self.token_usage
        if self.token_usage_log_id:
            result["token_usage_log_id"] = self.token_usage_log_id
        return result


class ContentPipeline:
    def __init__(
        self,
        trend_agent: TrendAgent | None = None,
        research_agent: ResearchAgent | None = None,
        content_writer: ContentWriterAgent | None = None,
        publishing_agent: PublishingAgent | None = None,
    ):
        self.trend_agent = trend_agent or TrendAgent()
        self.research_agent = research_agent or ResearchAgent()
        self.content_writer = content_writer or ContentWriterAgent()
        self._publishing_agent = publishing_agent

    def run(
        self,
        trend_prompt: str | None = None,
        publish: bool = False,
        publish_dry_run: bool = False,
        run_source: str = "pipeline",
    ) -> PipelineResult:
        prompt = trend_prompt or DEFAULT_TREND_PROMPT
        steps = ["trend", "research", "content_writer"]

        logger.info("ContentPipeline start publish=%s", publish)
        usage_tracker = PipelineTokenUsage()

        trends = self.trend_agent.run_agent(prompt)
        usage_tracker.add_agent("trend", self.trend_agent.last_token_usage)
        logger.info("ContentPipeline trend done count=%d", len(trends))

        research = self.research_agent.research_trends(trends)
        usage_tracker.add_agent("research", self.research_agent.last_token_usage)
        logger.info("ContentPipeline research done count=%d", len(research))

        content = self.content_writer.write_content(research)
        usage_tracker.add_agent("content_writer", self.content_writer.last_token_usage)
        logger.info("ContentPipeline content_writer done batch_id=%s", content.get("batch_id"))

        token_summary = usage_tracker.to_dict()
        log_token_usage(
            "ContentPipeline total",
            usage_tracker.total,
        )
        logger.info("ContentPipeline estimated_cost_usd=%s", token_summary["estimated_cost_usd"])

        publishing: dict[str, Any] | None = None
        publishing_error: str | None = None
        if publish:
            try:
                publisher = self._publishing_agent or PublishingAgent(dry_run=publish_dry_run)
                publishing = publisher.publish_items(
                    content.get("items", []),
                    source_batch_id=content.get("batch_id"),
                )
                steps.append("publishing")
                logger.info("ContentPipeline publish done published=%d", publishing.get("published", 0))
            except FacebookConnectorError as exc:
                publishing_error = str(exc)
                logger.warning("ContentPipeline publish failed: %s", publishing_error)

        token_log = save_token_usage_log(
            token_summary,
            run_source=run_source,
            content_batch_id=content.get("batch_id"),
            publish_batch_id=(publishing or {}).get("publish_batch_id"),
            pipeline_steps=steps,
            trends_count=len(trends),
            research_count=len(research),
            content_count=len(content.get("items", [])),
            published_count=(publishing or {}).get("published", 0),
            model=settings.CLAUDE_MODEL,
            publish_dry_run=publish_dry_run if publish else False,
        )

        return PipelineResult(
            pipeline=steps,
            trends=trends,
            research=research,
            content=content,
            publishing=publishing,
            publishing_error=publishing_error,
            token_usage=token_summary,
            token_usage_log_id=token_log.get("id") if token_log else None,
        )


def run_content_pipeline(
    trend_prompt: str | None = None,
    publish: bool = False,
    publish_dry_run: bool = False,
    run_source: str = "pipeline",
) -> dict[str, Any]:
    return ContentPipeline().run(
        trend_prompt=trend_prompt,
        publish=publish,
        publish_dry_run=publish_dry_run,
        run_source=run_source,
    ).to_dict()
