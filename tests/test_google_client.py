from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from document_translator.errors import PipelineError
from document_translator.lib.llm.google import GoogleLLMClient
from document_translator.lib.llm.protocol import LLMCallTracker


def test_google_requires_api_key() -> None:
    client = GoogleLLMClient(api_key=None)
    with pytest.raises(PipelineError, match="GOOGLE_API_KEY"):
        client.complete("system", "user")


def test_google_complete_success() -> None:
    mock_genai = MagicMock()
    mock_client = MagicMock()
    mock_genai.Client.return_value = mock_client
    mock_client.models.generate_content.return_value = MagicMock(
        text=" translated ",
        usage_metadata=MagicMock(prompt_token_count=60, candidates_token_count=15),
    )
    mock_errors = MagicMock()
    mock_errors.APIError = type("APIError", (Exception,), {"code": 500})
    tracker = LLMCallTracker()
    client = GoogleLLMClient(api_key="test-key", model="gemini-2.5-pro", tracker=tracker)

    with patch.dict("sys.modules", {"google": MagicMock(genai=mock_genai), "google.genai": mock_genai, "google.genai.errors": mock_errors}):
        text = client.complete("system", "user")

    assert text == "translated"
    assert tracker.count == 1
    assert tracker.input_tokens == 60
    assert tracker.output_tokens == 15


def test_google_retries_rate_limit() -> None:
    mock_genai = MagicMock()
    mock_client = MagicMock()
    mock_genai.Client.return_value = mock_client

    class RateLimitedError(Exception):
        code = 429

        def __init__(self) -> None:
            self.response = MagicMock(headers={"retry-after": "0"})

    rate_limited = RateLimitedError()
    mock_client.models.generate_content.side_effect = [
        rate_limited,
        MagicMock(text="ok"),
    ]
    client = GoogleLLMClient(api_key="test-key", max_retries=1, retry_base_delay=0.01)

    with (
        patch.dict("sys.modules", {"google": MagicMock(genai=mock_genai), "google.genai": mock_genai}),
        patch("document_translator.lib.llm.retry.time.sleep"),
    ):
        text = client.complete("system", "user")

    assert text == "ok"
    assert mock_client.models.generate_content.call_count == 2
