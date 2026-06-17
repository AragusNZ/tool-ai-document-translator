from __future__ import annotations

# Indicative USD pricing per 1M tokens (input, output). Updated periodically for dashboards.
_MODEL_PRICING_USD_PER_MILLION: dict[str, tuple[float, float]] = {
    "cursor:composer-2.5": (1.25, 10.00),
    "cursor:claude-opus-4-8-thinking-high": (15.00, 75.00),
    "cursor:gpt-5.5-medium": (2.50, 10.00),
    "openai:gpt-4o": (2.50, 10.00),
    "openai:gpt-4o-mini": (0.15, 0.60),
    "anthropic:claude-sonnet-4-6": (3.00, 15.00),
    "anthropic:claude-opus-4-6": (15.00, 75.00),
    "google:gemini-2.5-pro": (1.25, 10.00),
    "google:gemini-2.5-flash": (0.30, 2.50),
}


def estimate_llm_cost_usd(selector: str, input_tokens: int, output_tokens: int) -> float | None:
    pricing = _MODEL_PRICING_USD_PER_MILLION.get(selector)
    if pricing is None:
        return None
    input_rate, output_rate = pricing
    return round(
        (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000,
        6,
    )
