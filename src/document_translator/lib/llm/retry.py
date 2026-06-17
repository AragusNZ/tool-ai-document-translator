from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import TypeVar

from document_translator.config.defaults import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_RETRY_BASE_DELAY,
    DEFAULT_RETRY_MAX_DELAY,
)
from document_translator.observability.logging_setup import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


def parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    stripped = value.strip()
    try:
        return max(0.0, float(stripped))
    except ValueError:
        pass
    try:
        retry_at = parsedate_to_datetime(stripped)
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return None


def retry_delay_seconds(
    exc: object,
    attempt: int,
    *,
    base_delay: float = DEFAULT_RETRY_BASE_DELAY,
    max_delay: float = DEFAULT_RETRY_MAX_DELAY,
    retry_after_header: str | None = None,
) -> float:
    hinted = parse_retry_after(retry_after_header)
    if hinted is None:
        retry_after = getattr(exc, "retry_after", None)
        hinted = parse_retry_after(retry_after if isinstance(retry_after, str) else None)
    if hinted is not None:
        return min(hinted, max_delay)
    return min(base_delay * (2**attempt), max_delay)


def is_retryable_http_status(status_code: int) -> bool:
    return status_code == 408 or status_code == 429 or status_code >= 500


def retry_on_transient(
    operation: Callable[[], T],
    *,
    is_retryable: Callable[[Exception], bool],
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_RETRY_BASE_DELAY,
    max_delay: float = DEFAULT_RETRY_MAX_DELAY,
    retry_after_for: Callable[[Exception], str | None] | None = None,
    log_label: str = "LLM request",
) -> T:
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return operation()
        except Exception as exc:
            last_exc = exc
            if not is_retryable(exc) or attempt >= max_retries:
                raise
            retry_after = retry_after_for(exc) if retry_after_for else None
            delay = retry_delay_seconds(
                exc,
                attempt,
                base_delay=base_delay,
                max_delay=max_delay,
                retry_after_header=retry_after,
            )
            logger.warning(
                "%s transient error (attempt %s/%s); retrying in %.1fs: %s",
                log_label,
                attempt + 1,
                max_retries + 1,
                delay,
                exc,
            )
            time.sleep(delay)
    assert last_exc is not None
    raise last_exc
