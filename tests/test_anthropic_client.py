from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from document_translator.errors import PipelineError
from document_translator.lib.llm.anthropic import AnthropicLLMClient
from document_translator.lib.llm.protocol import LLMCallTracker


def test_anthropic_requires_api_key() -> None:
    client = AnthropicLLMClient(api_key=None)
    with pytest.raises(PipelineError, match="ANTHROPIC_API_KEY"):
        client.complete("system", "user")


def test_anthropic_complete_success() -> None:
    mock_anthropic = MagicMock()
    mock_client = MagicMock()
    mock_anthropic.Anthropic.return_value = mock_client
    block = MagicMock(text=" translated ")
    mock_client.messages.create.return_value = MagicMock(
        content=[block],
        usage=MagicMock(input_tokens=80, output_tokens=20),
    )
    tracker = LLMCallTracker()
    client = AnthropicLLMClient(api_key="test-key", model="claude-sonnet-4-6", tracker=tracker)

    with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
        text = client.complete("system", "user")

    assert text == "translated"
    assert tracker.count == 1
    assert tracker.input_tokens == 80
    assert tracker.output_tokens == 20


def test_anthropic_retries_rate_limit() -> None:
    mock_anthropic = MagicMock()
    mock_client = MagicMock()
    mock_anthropic.Anthropic.return_value = mock_client
    mock_anthropic.APIStatusError = type("APIStatusError", (Exception,), {})
    rate_limited = mock_anthropic.APIStatusError("rate limited")
    rate_limited.status_code = 429
    rate_limited.response = MagicMock(headers={"retry-after": "0"})
    block = MagicMock(text="ok")
    mock_client.messages.create.side_effect = [
        rate_limited,
        MagicMock(content=[block]),
    ]
    client = AnthropicLLMClient(api_key="test-key", max_retries=1, retry_base_delay=0.01)

    with (
        patch.dict("sys.modules", {"anthropic": mock_anthropic}),
        patch("document_translator.lib.llm.retry.time.sleep"),
    ):
        text = client.complete("system", "user")

    assert text == "ok"
    assert mock_client.messages.create.call_count == 2
