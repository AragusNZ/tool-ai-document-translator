from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from cursor_sdk import CursorAgentError, RateLimitError

from document_translator.errors import IssueCode, PipelineError
from document_translator.lib.llm import CursorLLMClient, MockLLMClient
from document_translator.lib.llm.protocol import LLMCallTracker
from document_translator.lib.llm.retry import parse_retry_after, retry_delay_seconds


def test_mock_llm_default_responses() -> None:
    mock = MockLLMClient(prefix="[EN] ")
    semantic = mock.complete("Check semantic equivalent", "text")
    assert "equivalent" in semantic or "{" in semantic
    assert mock.complete("Identify the primary language", "sample") == "es"
    assert mock.complete("You are a professional document translator.", "user text").startswith("[EN]")


def test_mock_llm_set_response() -> None:
    mock = MockLLMClient()
    mock.set_response("custom key", "custom response")
    assert mock.complete("system", "custom key in user") == "custom response"


def test_mock_llm_adjudicate_with_variant_in_user() -> None:
    mock = MockLLMClient(prefix="[EN] ")
    user = "Legal document: False\n\nVariant 1:\nFirst variant.\n\nVariant 2:\nSecond."
    result = mock.complete("You choose the best English translation", user)
    assert result == " 1:"


def test_cursor_llm_requires_api_key() -> None:
    with patch.dict(os.environ, {}, clear=True):
        client = CursorLLMClient(api_key=None)
        with pytest.raises(PipelineError, match="CURSOR_API_KEY"):
            client.complete("system", "user")


def test_cursor_llm_reads_api_key_from_env() -> None:
    with patch.dict(os.environ, {"CURSOR_API_KEY": "env-key"}):
        client = CursorLLMClient()
        assert client.api_key == "env-key"


def _mock_cursor_sdk() -> MagicMock:
    mock_sdk = MagicMock()
    mock_sdk.Agent = MagicMock()
    mock_sdk.AgentOptions = MagicMock(side_effect=lambda **kwargs: kwargs)
    mock_sdk.LocalAgentOptions = MagicMock(side_effect=lambda **kwargs: kwargs)
    mock_sdk.CursorAgentError = CursorAgentError
    mock_sdk.RateLimitError = RateLimitError
    return mock_sdk


def test_cursor_llm_complete_success() -> None:
    mock_sdk = _mock_cursor_sdk()
    mock_sdk.Agent.prompt.return_value = MagicMock(
        status="completed",
        result="  Translated text  ",
        id="run-123",
    )
    tracker = LLMCallTracker()
    client = CursorLLMClient(api_key="test-key", model="test-model", cwd=Path("/tmp"), tracker=tracker)

    with patch.dict(sys.modules, {"cursor_sdk": mock_sdk}):
        text = client.complete("system prompt", "user prompt")

    assert text == "Translated text"
    assert tracker.count == 1
    assert tracker.input_tokens > 0
    assert tracker.output_tokens > 0
    mock_sdk.Agent.prompt.assert_called_once()
    call_args = mock_sdk.Agent.prompt.call_args
    assert "system prompt" in call_args[0][0]
    assert "user prompt" in call_args[0][0]
    options = call_args[0][1]
    assert options["api_key"] == "test-key"
    assert options["model"] == "test-model"
    assert options["local"]["cwd"] == "/tmp"


def test_cursor_llm_sdk_startup_failure() -> None:
    mock_sdk = _mock_cursor_sdk()
    mock_sdk.Agent.prompt.side_effect = OSError("bridge not running")
    client = CursorLLMClient(api_key="test-key")

    with patch.dict(sys.modules, {"cursor_sdk": mock_sdk}):
        with pytest.raises(PipelineError, match="Cursor SDK startup failed") as exc_info:
            client.complete("system", "user")

    assert exc_info.value.code == IssueCode.PIPELINE_FAILED
    assert exc_info.value.cause is not None
    mock_sdk.Agent.prompt.assert_called_once()


def test_parse_retry_after_seconds() -> None:
    assert parse_retry_after("12.5") == 12.5
    assert parse_retry_after(None) is None


def test_retry_delay_honors_retry_after() -> None:
    exc = RateLimitError("rate limited", is_retryable=True, retry_after="30")
    assert retry_delay_seconds(exc, attempt=0, base_delay=1.0, max_delay=120.0) == 30.0


def test_retry_delay_exponential_fallback() -> None:
    exc = CursorAgentError("transient", is_retryable=True)
    assert retry_delay_seconds(exc, attempt=2, base_delay=1.0, max_delay=120.0) == 4.0


def test_cursor_llm_retries_rate_limit_then_succeeds() -> None:
    mock_sdk = _mock_cursor_sdk()
    rate_limited = RateLimitError("rate limited", is_retryable=True, retry_after="0")
    mock_sdk.Agent.prompt.side_effect = [
        rate_limited,
        MagicMock(status="completed", result="ok", id="run-retry"),
    ]
    client = CursorLLMClient(api_key="test-key", max_retries=2, retry_base_delay=0.01)

    with (
        patch.dict(sys.modules, {"cursor_sdk": mock_sdk}),
        patch("document_translator.lib.llm.cursor.time.sleep") as sleep_mock,
    ):
        text = client.complete("system", "user")

    assert text == "ok"
    assert mock_sdk.Agent.prompt.call_count == 2
    sleep_mock.assert_called_once_with(0.0)


def test_cursor_llm_rate_limit_exhausted() -> None:
    mock_sdk = _mock_cursor_sdk()
    rate_limited = RateLimitError("rate limited", is_retryable=True, retry_after="0")
    mock_sdk.Agent.prompt.side_effect = rate_limited
    client = CursorLLMClient(api_key="test-key", max_retries=1, retry_base_delay=0.01)

    with (
        patch.dict(sys.modules, {"cursor_sdk": mock_sdk}),
        patch("document_translator.lib.llm.cursor.time.sleep"),
    ):
        with pytest.raises(PipelineError, match="Cursor SDK request failed") as exc_info:
            client.complete("system", "user")

    assert exc_info.value.code == IssueCode.PIPELINE_FAILED
    assert isinstance(exc_info.value.cause, RateLimitError)
    assert mock_sdk.Agent.prompt.call_count == 2


def test_cursor_llm_non_retryable_error_fails_immediately() -> None:
    mock_sdk = _mock_cursor_sdk()
    mock_sdk.Agent.prompt.side_effect = CursorAgentError("bad request", is_retryable=False)
    client = CursorLLMClient(api_key="test-key", max_retries=3)

    with patch.dict(sys.modules, {"cursor_sdk": mock_sdk}):
        with pytest.raises(PipelineError, match="Cursor SDK request failed"):
            client.complete("system", "user")

    mock_sdk.Agent.prompt.assert_called_once()


def test_cursor_llm_agent_error_status() -> None:
    mock_sdk = _mock_cursor_sdk()
    mock_sdk.Agent.prompt.return_value = MagicMock(status="error", result="", id="run-err")
    client = CursorLLMClient(api_key="test-key")

    with patch.dict(sys.modules, {"cursor_sdk": mock_sdk}):
        with pytest.raises(PipelineError, match="Cursor agent run failed") as exc_info:
            client.complete("system", "user")

    assert exc_info.value.scope["run_id"] == "run-err"


def test_cursor_llm_empty_response() -> None:
    mock_sdk = _mock_cursor_sdk()
    mock_sdk.Agent.prompt.return_value = MagicMock(status="completed", result="   ", id="run-empty")
    client = CursorLLMClient(api_key="test-key")

    with patch.dict(sys.modules, {"cursor_sdk": mock_sdk}):
        with pytest.raises(PipelineError, match="empty response"):
            client.complete("system", "user")
