from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class LLMProvider(str, Enum):
    CURSOR = "cursor"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"


@dataclass(frozen=True)
class LLMEntry:
    provider: LLMProvider
    model: str
    label: str
    env_key: str


SUPPORTED_LLMS: tuple[LLMEntry, ...] = (
    LLMEntry(LLMProvider.CURSOR, "composer-2.5", "Cursor Composer 2.5", "CURSOR_API_KEY"),
    LLMEntry(
        LLMProvider.CURSOR,
        "claude-opus-4-8-thinking-high",
        "Cursor Claude Opus 4.8",
        "CURSOR_API_KEY",
    ),
    LLMEntry(LLMProvider.CURSOR, "gpt-5.5-medium", "Cursor GPT 5.5 Medium", "CURSOR_API_KEY"),
    LLMEntry(LLMProvider.OPENAI, "gpt-4o", "OpenAI GPT-4o", "OPENAI_API_KEY"),
    LLMEntry(LLMProvider.OPENAI, "gpt-4o-mini", "OpenAI GPT-4o Mini", "OPENAI_API_KEY"),
    LLMEntry(
        LLMProvider.ANTHROPIC,
        "claude-sonnet-4-6",
        "Anthropic Claude Sonnet 4.6",
        "ANTHROPIC_API_KEY",
    ),
    LLMEntry(
        LLMProvider.ANTHROPIC,
        "claude-opus-4-6",
        "Anthropic Claude Opus 4.6",
        "ANTHROPIC_API_KEY",
    ),
    LLMEntry(LLMProvider.GOOGLE, "gemini-2.5-pro", "Google Gemini 2.5 Pro", "GOOGLE_API_KEY"),
    LLMEntry(LLMProvider.GOOGLE, "gemini-2.5-flash", "Google Gemini 2.5 Flash", "GOOGLE_API_KEY"),
)

_PROVIDER_ENV_KEYS: dict[LLMProvider, str] = {
    LLMProvider.CURSOR: "CURSOR_API_KEY",
    LLMProvider.OPENAI: "OPENAI_API_KEY",
    LLMProvider.ANTHROPIC: "ANTHROPIC_API_KEY",
    LLMProvider.GOOGLE: "GOOGLE_API_KEY",
}

_IMPLEMENTED_PROVIDERS: frozenset[LLMProvider] = frozenset(
    {LLMProvider.CURSOR, LLMProvider.OPENAI, LLMProvider.ANTHROPIC, LLMProvider.GOOGLE}
)


def format_llm_selector(provider: LLMProvider, model: str) -> str:
    return f"{provider.value}:{model}"


def parse_llm_selector(value: str) -> tuple[LLMProvider, str]:
    stripped = value.strip()
    if not stripped:
        raise ValueError("LLM selector must not be empty")

    if ":" in stripped:
        provider_part, model = stripped.split(":", 1)
        provider_key = provider_part.strip().lower()
        model = model.strip()
        if not provider_key or not model:
            raise ValueError(f"Invalid LLM selector: {value!r}")
        try:
            provider = LLMProvider(provider_key)
        except ValueError as exc:
            valid = ", ".join(p.value for p in LLMProvider)
            raise ValueError(
                f"Unknown LLM provider {provider_part!r}; expected one of: {valid}"
            ) from exc
        return provider, model

    return LLMProvider.CURSOR, stripped


def resolve_llm_selector(value: str) -> str:
    provider, model = parse_llm_selector(value)
    return format_llm_selector(provider, model)


def supported_llms(*, implemented_only: bool = True) -> list[dict[str, str]]:
    entries = SUPPORTED_LLMS
    if implemented_only:
        entries = tuple(e for e in entries if e.provider in _IMPLEMENTED_PROVIDERS)
    return [
        {
            "id": format_llm_selector(entry.provider, entry.model),
            "provider": entry.provider.value,
            "model": entry.model,
            "label": entry.label,
            "env_key": entry.env_key,
        }
        for entry in entries
    ]


def is_supported_llm(selector: str) -> bool:
    try:
        provider, model = parse_llm_selector(selector)
    except ValueError:
        return False
    if provider == LLMProvider.CURSOR:
        return bool(model)
    return any(entry.provider == provider and entry.model == model for entry in SUPPORTED_LLMS)


def provider_env_key(provider: LLMProvider) -> str:
    return _PROVIDER_ENV_KEYS[provider]


def validate_llm_selector(selector: str) -> str:
    provider, model = parse_llm_selector(selector)
    resolved = format_llm_selector(provider, model)
    if provider != LLMProvider.CURSOR and not is_supported_llm(resolved):
        known = ", ".join(entry["id"] for entry in supported_llms())
        raise ValueError(f"Unsupported LLM {resolved!r}; known options: {known}")
    return resolved
