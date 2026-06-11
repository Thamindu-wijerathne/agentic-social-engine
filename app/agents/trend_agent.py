import logging
import json
from typing import Any

from langchain.agents import create_agent

from app.core.llm import main_llm
from app.prompts.PromptManager import PromptManager
from app.tools.trend_agent.animal_news_scraper_tool import animal_news_scraper_tool
from app.tools.trend_agent.gnews_tool import gnews_tool
from app.tools.trend_agent.googlenews_tool import googlenews_tool

logger = logging.getLogger(__name__)
TOPIC_POOL_MAX = 10
TOPIC_RETURN_COUNT = 5


def _summarize_invoke_result(result: Any) -> str:
    if not isinstance(result, dict):
        return f"type={type(result).__name__}"

    messages = result.get("messages", [])
    parts = [f"message_count={len(messages)}"]

    if messages:
        last = messages[-1]
        content = getattr(last, "content", None)
        if content is not None:
            preview = str(content)[:200].replace("\n", " ")
            parts.append(f"last_message_preview={preview!r}")

    return " ".join(parts)


class TrendAgent:
    def __init__(self):
        logger.info("Initializing TrendAgent")
        self.llm = main_llm
        self.agent = self.create_agent()
        logger.info("TrendAgent ready")

    def create_agent(self):
        logger.debug("Loading system prompt and creating agent graph")
        system_prompt = PromptManager.get("agent_prompts", "trend_agent_system_prompt")
        logger.info("System prompt loaded (%d chars)", len(system_prompt))
        return create_agent(
            self.llm,
            tools=[googlenews_tool, gnews_tool, animal_news_scraper_tool],
            system_prompt=system_prompt,
        )

    def _extract_json_payload(self, text: str) -> Any:
        # Try direct parse first.
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Fallback: parse first JSON array/object embedded in free text.
        decoder = json.JSONDecoder()
        for start_char in ("[", "{"):
            start = text.find(start_char)
            while start != -1:
                try:
                    obj, _ = decoder.raw_decode(text[start:])
                    return obj
                except json.JSONDecodeError:
                    start = text.find(start_char, start + 1)
        return None

    def _extract_topic_scores(self, response: dict[str, Any]) -> list[dict[str, Any]]:
        messages = response.get("messages", [])
        if not messages:
            return []

        last_content = getattr(messages[-1], "content", "")
        if not isinstance(last_content, str):
            last_content = str(last_content)

        parsed = self._extract_json_payload(last_content)
        if parsed is None:
            logger.warning("Could not parse agent output as JSON payload")
            return []

        if not isinstance(parsed, list):
            return []

        topic_scores: list[dict[str, Any]] = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            topic = item.get("topic")
            trend_score = item.get("trend_score")
            if topic is None or trend_score is None:
                continue
            normalized_item = {"topic": topic, "trend_score": trend_score}

            # Preserve useful metadata for downstream UI/rendering.
            for key in ("status", "description", "mentions", "sources", "top_items", "entities", "keywords", "category"):
                if key in item:
                    normalized_item[key] = item[key]

            topic_scores.append(normalized_item)

        # Keep candidate pool bounded, then return best 5.
        sorted_topics = sorted(
            topic_scores,
            key=lambda x: float(x.get("trend_score", 0)),
            reverse=True,
        )[:TOPIC_POOL_MAX]
        return sorted_topics[:TOPIC_RETURN_COUNT]

    def run_agent(self, input: str) -> list[dict[str, Any]]:
        logger.info("Agent invoke start input=%r", input)
        response = self.agent.invoke({
            "messages": [("user", input)],
        })
        logger.info("Agent invoke done %s", _summarize_invoke_result(response))
        topic_scores = self._extract_topic_scores(response)
        logger.info("Extracted topic_scores count=%d", len(topic_scores))
        return topic_scores
