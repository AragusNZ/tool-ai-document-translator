from __future__ import annotations

import hashlib
import hmac
import json
import urllib.error
import urllib.request
from typing import Any

from document_translator import __version__
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


def deliver_terminal_webhook(
    url: str,
    result: JobResult,
    *,
    secret: str | None = None,
    timeout_seconds: float = 30.0,
) -> None:
    payload = build_terminal_webhook_payload(result)
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": _USER_AGENT,
    }
    if secret:
        headers[_SIGNATURE_HEADER] = sign_webhook_body(body, secret)

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
