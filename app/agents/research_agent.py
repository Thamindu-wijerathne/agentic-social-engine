import json
import logging
from typing import Any

from langchain.agents import create_agent

from app.core.image_urls import filter_public_image_urls
from app.core.json_utils import extract_json_payload
from app.core.llm import main_llm
from app.core.token_usage import TokenUsage, extract_usage_from_agent_response, log_token_usage, summarize_invoke_result
from app.prompts.PromptManager import PromptManager

logger = logging.getLogger(__name__)


class ResearchAgent:
    def __init__(self):
        logger.info("Initializing ResearchAgent")
        self.llm = main_llm
        self.agent = self.create_agent()
        self.last_token_usage = TokenUsage()
        logger.info("ResearchAgent ready")

    def create_agent(self):
        logger.debug("Loading system prompt and creating agent graph")
        system_prompt = PromptManager.get("agent_prompts", "research_agent_system_prompt")
        logger.info("System prompt loaded (%d chars)", len(system_prompt))
        return create_agent(
            self.llm,
            tools=[],
            system_prompt=system_prompt,
        )

    @staticmethod
    def _extract_last_message_content(response: dict[str, Any]) -> str:
        messages = response.get("messages", [])
        if not messages:
            return ""

        content = getattr(messages[-1], "content", "")
        if isinstance(content, list):
            return "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )
        return str(content)

    def _normalize_items(self, parsed: Any) -> list[dict[str, Any]]:
        if isinstance(parsed, dict):
            items = (
                parsed.get("topics")
                or parsed.get("items")
                or parsed.get("research")
                or parsed.get("reseach")
            )
            if isinstance(items, list):
                parsed = items
            else:
                parsed = [parsed]

        if not isinstance(parsed, list):
            return []

        normalized: list[dict[str, Any]] = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            topic = item.get("topic")
            if not topic:
                continue
            raw_img_urls = item.get("img_urls", item.get("image_urls", []))
            if not isinstance(raw_img_urls, list):
                raw_img_urls = [raw_img_urls] if raw_img_urls else []
            img_urls = filter_public_image_urls(raw_img_urls)
            if not img_urls:
                logger.warning("ResearchAgent skipped item without valid img_urls topic=%r", str(topic)[:80])
                continue

            entry: dict[str, Any] = {
                "topic": topic,
                "description": str(item.get("description", "")),
                "context": str(item.get("context", "")),
                "img_urls": img_urls,
            }
            category = item.get("category")
            if category:
                entry["category"] = category
            normalized.append(entry)
        return normalized

    def research_trends(self, trends: list[dict[str, Any]]) -> list[dict[str, Any]]:
        logger.info("Agent invoke start trends=%d", len(trends))
        user_payload = json.dumps(trends, ensure_ascii=False)
        response = self.agent.invoke({
            "messages": [("user", user_payload)],
        })
        self.last_token_usage = extract_usage_from_agent_response(response)
        log_token_usage("ResearchAgent", self.last_token_usage)
        logger.info("Agent invoke done %s", summarize_invoke_result(response))

        content = self._extract_last_message_content(response)
        parsed = extract_json_payload(content)
        if parsed is None:
            logger.error("ResearchAgent failed to extract JSON from LLM response; raw content: %s", content[:500])
            raise ValueError("ResearchAgent: LLM response contained no parseable JSON")

        items = self._normalize_items(parsed)
        if not items:
            logger.error("ResearchAgent parsed JSON but found no valid items; parsed=%r", parsed)
            raise ValueError("ResearchAgent: JSON parsed but contained no valid topic items")

        logger.info("ResearchAgent complete items=%d", len(items))
        return items
