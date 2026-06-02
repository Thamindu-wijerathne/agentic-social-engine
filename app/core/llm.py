from langchain_anthropic import ChatAnthropic

from config.settings import settings

main_llm = ChatAnthropic(
    model=settings.CLAUDE_MODEL,
    api_key=settings.CLAUDE_API_KEY,
)

fast_llm = ChatAnthropic(
    model=settings.CLAUDE_MODEL_FAST,
    api_key=settings.CLAUDE_API_KEY,
)
