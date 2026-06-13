import json
import logging
from typing import Any

from app.core.json_utils import extract_json_payload
from app.core.llm import main_llm
from app.core.token_usage import TokenUsage, extract_usage_from_message, log_token_usage
from app.prompts.PromptManager import PromptManager

logger = logging.getLogger(__name__)


class ResearchAgent:
    def __init__(self):
        self.llm = main_llm
        self.system_prompt = PromptManager.get("agent_prompts", "research_agent_system_prompt")
        self.last_token_usage = TokenUsage()

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
            img_urls = item.get("img_urls", item.get("image_urls", []))
            if not isinstance(img_urls, list):
                img_urls = [img_urls] if img_urls else []
            img_urls = [u for u in img_urls if u]

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
        logger.info("ResearchAgent start trends=%d", len(trends))
        user_payload = json.dumps(trends, ensure_ascii=False)
        response = self.llm.invoke(
            [
                ("system", self.system_prompt),
                ("user", user_payload),
            ]
        )
        self.last_token_usage = extract_usage_from_message(response) or TokenUsage()
        log_token_usage("ResearchAgent", self.last_token_usage)

        content = getattr(response, "content", "")
        if isinstance(content, list):
            content = "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )
        else:
            content = str(content)

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
