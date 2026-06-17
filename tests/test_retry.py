from __future__ import annotations

from datetime import UTC
from unittest.mock import patch

import pytest

from document_translator.lib.llm.retry import (
    is_retryable_http_status,
    parse_retry_after,
    retry_delay_seconds,
    retry_on_transient,
)


def test_parse_retry_after_http_date() -> None:
    with patch("document_translator.lib.llm.retry.datetime") as mock_dt:
        from datetime import datetime

        mock_dt.now.return_value = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        mock_dt.now.side_effect = None
        # Wed, 21 Oct 2015 07:28:00 GMT is in the past relative to mock now
        result = parse_retry_after("Wed, 21 Oct 2015 07:28:00 GMT")
    assert result == 0.0


def test_parse_retry_after_invalid_returns_none() -> None:
    assert parse_retry_after("not-a-date-or-number") is None


def test_retry_delay_seconds_exponential_backoff() -> None:
    assert retry_delay_seconds(RuntimeError("fail"), 0, base_delay=1.0, max_delay=10.0) == 1.0
    assert retry_delay_seconds(RuntimeError("fail"), 2, base_delay=1.0, max_delay=10.0) == 4.0
    assert retry_delay_seconds(RuntimeError("fail"), 5, base_delay=1.0, max_delay=10.0) == 10.0


def test_is_retryable_http_status() -> None:
    assert is_retryable_http_status(408) is True
    assert is_retryable_http_status(429) is True
    assert is_retryable_http_status(500) is True
    assert is_retryable_http_status(404) is False


def test_retry_on_transient_succeeds_after_retry() -> None:
    attempts = {"count": 0}

    def flaky() -> str:
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise RuntimeError("transient")
        return "ok"

    with patch("document_translator.lib.llm.retry.time.sleep"):
        result = retry_on_transient(
            flaky,
            is_retryable=lambda exc: isinstance(exc, RuntimeError),
            max_retries=2,
            base_delay=0.01,
        )

    assert result == "ok"
    assert attempts["count"] == 2


def test_retry_on_transient_raises_when_exhausted() -> None:
    def always_fail() -> str:
        raise RuntimeError("permanent")

    with patch("document_translator.lib.llm.retry.time.sleep"):
        with pytest.raises(RuntimeError, match="permanent"):
            retry_on_transient(
                always_fail,
                is_retryable=lambda exc: isinstance(exc, RuntimeError),
                max_retries=1,
                base_delay=0.01,
            )


def test_retry_on_transient_non_retryable_raises_immediately() -> None:
    attempts = {"count": 0}

    def fail() -> str:
        attempts["count"] += 1
        raise ValueError("bad request")

    with pytest.raises(ValueError, match="bad request"):
        retry_on_transient(
            fail,
            is_retryable=lambda exc: isinstance(exc, RuntimeError),
            max_retries=3,
        )

    assert attempts["count"] == 1
