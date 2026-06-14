import logging
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from app.agents.content_writer_agent import ContentWriterAgent
from app.agents.publishing_agent import PublishingAgent
from app.agents.research_agent import ResearchAgent
from app.agents.trend_agent import TrendAgent
from app.connectors.fb_connector import FacebookConnectorError

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

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "pipeline": self.pipeline,
            "trends": {"count": len(self.trends), "items": self.trends},
            "research": {"count": len(self.research), "items": self.research},
            "content": self.content,
        }
        if self.publishing is not None:
            result["publishing"] = self.publishing
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
    ) -> PipelineResult:
        prompt = trend_prompt or DEFAULT_TREND_PROMPT
        steps = ["trend", "research", "content_writer"]

        logger.info("ContentPipeline start publish=%s", publish)

        trends = self.trend_agent.run_agent(prompt)
        logger.info("ContentPipeline trend done count=%d", len(trends))

        research = self.research_agent.research_trends(trends)
        logger.info("ContentPipeline research done count=%d", len(research))

        content = self.content_writer.write_content(research)
        logger.info("ContentPipeline content_writer done batch_id=%s", content.get("batch_id"))

        publishing: dict[str, Any] | None = None
        if publish:
            publisher = self._publishing_agent or PublishingAgent()
            publishing = publisher.publish_items(
                content.get("items", []),
                source_batch_id=content.get("batch_id"),
            )
            steps.append("publishing")
            logger.info("ContentPipeline publish done published=%d", publishing.get("published", 0))

        return PipelineResult(
            pipeline=steps,
            trends=trends,
            research=research,
            content=content,
            publishing=publishing,
        )


def run_content_pipeline(
    trend_prompt: str | None = None,
    publish: bool = False,
) -> dict[str, Any]:
    try:
        result = ContentPipeline().run(trend_prompt=trend_prompt, publish=publish)
    except FacebookConnectorError as exc:
        raise ValueError(f"Publishing failed: {exc}") from exc
    return result.to_dict()
