from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from document_translator.errors import PipelineError
from document_translator.lib.llm.openai import OpenAILLMClient
from document_translator.lib.llm.protocol import LLMCallTracker
from document_translator.lib.llm.retry import parse_retry_after, retry_delay_seconds


def test_openai_requires_api_key() -> None:
    client = OpenAILLMClient(api_key=None)
    with pytest.raises(PipelineError, match="OPENAI_API_KEY"):
        client.complete("system", "user")


def test_openai_complete_success() -> None:
    mock_openai = MagicMock()
    mock_client = MagicMock()
    mock_openai.OpenAI.return_value = mock_client
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=" translated "))],
        usage=MagicMock(prompt_tokens=120, completion_tokens=30),
    )
    tracker = LLMCallTracker()
    client = OpenAILLMClient(api_key="test-key", model="gpt-4o", tracker=tracker)

    with patch.dict("sys.modules", {"openai": mock_openai}):
        text = client.complete("system", "user")

    assert text == "translated"
    assert tracker.count == 1
    assert tracker.input_tokens == 120
    assert tracker.output_tokens == 30


def test_openai_retries_rate_limit() -> None:
    mock_openai = MagicMock()
    mock_client = MagicMock()
    mock_openai.OpenAI.return_value = mock_client
    mock_openai.APIStatusError = type("APIStatusError", (Exception,), {})
    rate_limited = mock_openai.APIStatusError("rate limited")
    rate_limited.status_code = 429
    rate_limited.response = MagicMock(headers={"retry-after": "0"})
    mock_client.chat.completions.create.side_effect = [
        rate_limited,
        MagicMock(choices=[MagicMock(message=MagicMock(content="ok"))]),
    ]
    client = OpenAILLMClient(api_key="test-key", max_retries=1, retry_base_delay=0.01)

    with (
        patch.dict("sys.modules", {"openai": mock_openai}),
        patch("document_translator.lib.llm.retry.time.sleep"),
    ):
        text = client.complete("system", "user")

    assert text == "ok"
    assert mock_client.chat.completions.create.call_count == 2


def test_retry_helpers_reexported_for_cursor_tests() -> None:
    assert parse_retry_after("12.5") == 12.5
    exc = MagicMock(retry_after="30")
    assert retry_delay_seconds(exc, 0, base_delay=1.0, max_delay=120.0) == 30.0
