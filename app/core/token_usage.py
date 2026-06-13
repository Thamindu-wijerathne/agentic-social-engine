import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Approximate Claude Sonnet 4 pricing (USD per 1M tokens) — update if your model/pricing changes.
DEFAULT_INPUT_PRICE_PER_MTOK = 3.0
DEFAULT_OUTPUT_PRICE_PER_MTOK = 15.0


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    llm_calls: int = 0

    def add(self, input_tokens: int = 0, output_tokens: int = 0, calls: int = 1) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.total_tokens += input_tokens + output_tokens
        self.llm_calls += calls

    def merge(self, other: "TokenUsage") -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.total_tokens += other.total_tokens
        self.llm_calls += other.llm_calls

    def to_dict(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "llm_calls": self.llm_calls,
        }


@dataclass
class PipelineTokenUsage:
    by_agent: dict[str, TokenUsage] = field(default_factory=dict)

    def add_agent(self, agent: str, usage: TokenUsage) -> None:
        if agent not in self.by_agent:
            self.by_agent[agent] = TokenUsage()
        self.by_agent[agent].merge(usage)

    @property
    def total(self) -> TokenUsage:
        combined = TokenUsage()
        for usage in self.by_agent.values():
            combined.merge(usage)
        return combined

    def estimated_cost_usd(
        self,
        input_price_per_mtok: float = DEFAULT_INPUT_PRICE_PER_MTOK,
        output_price_per_mtok: float = DEFAULT_OUTPUT_PRICE_PER_MTOK,
    ) -> float:
        total = self.total
        input_cost = (total.input_tokens / 1_000_000) * input_price_per_mtok
        output_cost = (total.output_tokens / 1_000_000) * output_price_per_mtok
        return round(input_cost + output_cost, 6)

    def to_dict(self) -> dict[str, Any]:
        return {
            "by_agent": {name: usage.to_dict() for name, usage in self.by_agent.items()},
            "total": self.total.to_dict(),
            "estimated_cost_usd": self.estimated_cost_usd(),
        }


def _read_int(data: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = data.get(key)
        if isinstance(value, int):
            return value
    return 0


def extract_usage_from_message(message: Any) -> TokenUsage | None:
    """Extract token usage from a LangChain AIMessage or similar object."""
    usage_meta = getattr(message, "usage_metadata", None)
    if isinstance(usage_meta, dict) and usage_meta:
        input_tokens = _read_int(usage_meta, "input_tokens", "prompt_tokens")
        output_tokens = _read_int(usage_meta, "output_tokens", "completion_tokens")
        total_tokens = _read_int(usage_meta, "total_tokens")
        if not total_tokens:
            total_tokens = input_tokens + output_tokens
        if input_tokens or output_tokens or total_tokens:
            return TokenUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                llm_calls=1,
            )

    response_meta = getattr(message, "response_metadata", None)
    if isinstance(response_meta, dict):
        for key in ("usage", "token_usage", "usage_metadata"):
            nested = response_meta.get(key)
            if isinstance(nested, dict):
                usage = extract_usage_from_dict(nested)
                if usage.total_tokens or usage.input_tokens or usage.output_tokens:
                    usage.llm_calls = 1
                    return usage

    return None


def extract_usage_from_dict(data: dict[str, Any]) -> TokenUsage:
    input_tokens = _read_int(data, "input_tokens", "prompt_tokens")
    output_tokens = _read_int(data, "output_tokens", "completion_tokens")
    total_tokens = _read_int(data, "total_tokens")
    if not total_tokens:
        total_tokens = input_tokens + output_tokens
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )


def extract_usage_from_agent_response(response: dict[str, Any]) -> TokenUsage:
    """Sum usage across all LLM turns in a LangChain agent invoke result."""
    combined = TokenUsage()
    messages = response.get("messages", [])
    for message in messages:
        usage = extract_usage_from_message(message)
        if usage:
            combined.merge(usage)
    return combined


def log_token_usage(label: str, usage: TokenUsage) -> None:
    logger.info(
        "%s tokens input=%d output=%d total=%d calls=%d",
        label,
        usage.input_tokens,
        usage.output_tokens,
        usage.total_tokens,
        usage.llm_calls,
    )
