from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request
from typing import Any

from document_translator import __version__
from document_translator.config.defaults import (
    DEFAULT_WEBHOOK_MAX_RETRIES,
    DEFAULT_WEBHOOK_RETRY_BASE_DELAY,
)
from document_translator.models import JobResult

_SIGNATURE_HEADER = "X-Document-Translator-Signature"
_USER_AGENT = f"document-translator/{__version__}"


def build_terminal_webhook_payload(result: JobResult) -> dict[str, Any]:
    return {
        "event": "job.terminal",
        "job": result.model_dump_json_api(),
    }


def sign_webhook_body(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _deliver_once(
    url: str,
    body: bytes,
    headers: dict[str, str],
    *,
    timeout_seconds: float,
) -> None:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            status = getattr(response, "status", response.getcode())
            if status is not None and int(status) >= 400:
                raise RuntimeError(f"webhook returned HTTP {status}")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"webhook returned HTTP {exc.code}: {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"webhook request failed: {exc.reason}") from exc


def deliver_terminal_webhook(
    url: str,
    result: JobResult,
    *,
    secret: str | None = None,
    timeout_seconds: float = 30.0,
    max_retries: int = DEFAULT_WEBHOOK_MAX_RETRIES,
    retry_base_delay: float = DEFAULT_WEBHOOK_RETRY_BASE_DELAY,
) -> None:
    payload = build_terminal_webhook_payload(result)
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": _USER_AGENT,
    }
    if secret:
        headers[_SIGNATURE_HEADER] = sign_webhook_body(body, secret)

    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            _deliver_once(url, body, headers, timeout_seconds=timeout_seconds)
        except RuntimeError as exc:
            last_exc = exc
            if attempt >= max_retries:
                raise
            time.sleep(retry_base_delay * (2**attempt))
        else:
            return

    assert last_exc is not None
    raise last_exc
