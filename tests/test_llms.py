from __future__ import annotations

import pytest

from document_translator.config.llms import (
    LLMProvider,
    format_llm_selector,
    is_supported_llm,
    parse_llm_selector,
    resolve_llm_selector,
    supported_llms,
    validate_llm_selector,
)


def test_parse_llm_selector_provider_model() -> None:
    provider, model = parse_llm_selector("cursor:composer-2.5")
    assert provider == LLMProvider.CURSOR
    assert model == "composer-2.5"


def test_parse_llm_selector_bare_model_defaults_to_cursor() -> None:
    provider, model = parse_llm_selector("composer-2.5")
    assert provider == LLMProvider.CURSOR
    assert model == "composer-2.5"


def test_parse_llm_selector_invalid_provider() -> None:
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        parse_llm_selector("unknown:gpt-4o")


def test_resolve_llm_selector_normalizes() -> None:
    assert resolve_llm_selector("composer-2.5") == "cursor:composer-2.5"
    assert resolve_llm_selector("openai:gpt-4o") == "openai:gpt-4o"


def test_supported_llms_shape() -> None:
    entries = supported_llms()
    assert entries
    first = entries[0]
    assert {"id", "provider", "model", "label", "env_key"} <= set(first)


def test_is_supported_llm_cursor_accepts_any_model() -> None:
    assert is_supported_llm("cursor:custom-model")
    assert not is_supported_llm("openai:unknown-model")


def test_is_supported_llm_catalogued_provider_model() -> None:
    assert is_supported_llm("openai:gpt-4o")
    assert is_supported_llm("anthropic:claude-sonnet-4-6")


def test_validate_llm_selector_rejects_unknown_non_cursor() -> None:
    with pytest.raises(ValueError, match="Unsupported LLM"):
        validate_llm_selector("openai:not-a-real-model")


def test_format_llm_selector() -> None:
    assert format_llm_selector(LLMProvider.ANTHROPIC, "claude-sonnet-4-6") == (
        "anthropic:claude-sonnet-4-6"
    )
