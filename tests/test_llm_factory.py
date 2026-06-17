from __future__ import annotations

from unittest.mock import patch

import pytest

from document_translator.config.settings import PipelineConfig
from document_translator.errors import IssueCode, PipelineError
from document_translator.lib.llm import CursorLLMClient
from document_translator.lib.llm.factory import build_llm_client
from document_translator.lib.llm.protocol import LLMCallTracker


def test_build_llm_client_cursor() -> None:
    config = PipelineConfig(llm="cursor:composer-2.5", cursor_api_key="test-key")
    client = build_llm_client(config, tracker=LLMCallTracker(), cwd=config.root)
    assert isinstance(client, CursorLLMClient)
    assert client.model == "composer-2.5"
    assert client.api_key == "test-key"


def test_build_llm_client_translation_model_compat() -> None:
    config = PipelineConfig(translation_model="gpt-5.5-medium", cursor_api_key="test-key")
    assert config.llm == "cursor:gpt-5.5-medium"
    client = build_llm_client(config, tracker=LLMCallTracker(), cwd=config.root)
    assert isinstance(client, CursorLLMClient)
    assert client.model == "gpt-5.5-medium"


def test_build_llm_client_openai() -> None:
    config = PipelineConfig(llm="openai:gpt-4o", openai_api_key="openai-key")
    client = build_llm_client(config, tracker=LLMCallTracker(), cwd=config.root)
    from document_translator.lib.llm.openai import OpenAILLMClient

    assert isinstance(client, OpenAILLMClient)
    assert client.model == "gpt-4o"


def test_build_llm_client_missing_optional_dependency() -> None:
    config = PipelineConfig(llm="openai:gpt-4o", openai_api_key="openai-key")
    with patch("document_translator.lib.llm.factory.import_module", side_effect=ImportError("no openai")):
        with pytest.raises(PipelineError, match="optional dependency") as exc_info:
            build_llm_client(config, tracker=LLMCallTracker(), cwd=config.root)
    assert exc_info.value.code == IssueCode.CONFIGURATION_ERROR


def test_build_llm_client_anthropic() -> None:
    config = PipelineConfig(llm="anthropic:claude-sonnet-4-6", anthropic_api_key="anthropic-key")
    client = build_llm_client(config, tracker=LLMCallTracker(), cwd=config.root)
    from document_translator.lib.llm.anthropic import AnthropicLLMClient

    assert isinstance(client, AnthropicLLMClient)
    assert client.model == "claude-sonnet-4-6"


def test_build_llm_client_google() -> None:
    config = PipelineConfig(llm="google:gemini-2.5-pro", google_api_key="google-key")
    client = build_llm_client(config, tracker=LLMCallTracker(), cwd=config.root)
    from document_translator.lib.llm.google import GoogleLLMClient

    assert isinstance(client, GoogleLLMClient)
    assert client.model == "gemini-2.5-pro"
