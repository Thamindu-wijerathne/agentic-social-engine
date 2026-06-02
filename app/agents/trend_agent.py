import logging
from typing import Any

from langchain.agents import create_agent

from app.core.llm import main_llm
from app.prompts.PromptManager import PromptManager
from app.tools.trend_agent.googlenews_tool import googlenews_tool

logger = logging.getLogger(__name__)


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
            tools=[googlenews_tool],
            system_prompt=system_prompt,
        )

    def run_agent(self, input: str):
        logger.info("Agent invoke start input=%r", input)
        response = self.agent.invoke({
            "messages": [("user", input)],
        })
        logger.info("Agent invoke done %s", _summarize_invoke_result(response))
        return response
