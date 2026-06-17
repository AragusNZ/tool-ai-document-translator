from __future__ import annotations

import re
from typing import Any

_SECRET_PATTERNS = (
    re.compile(r"(api[_-]?key|secret|token|password)\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"Bearer\s+\S+", re.IGNORECASE),
)


def _scrub_text(value: str) -> str:
    scrubbed = value
    for pattern in _SECRET_PATTERNS:
        scrubbed = pattern.sub("<redacted>", scrubbed)
    return scrubbed


def scrub_sentry_event(event: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any] | None:
    message = event.get("message")
    if isinstance(message, str):
        event["message"] = _scrub_text(message)

    exception = event.get("exception")
    if isinstance(exception, dict):
        for value in exception.get("values", []):
            if isinstance(value, dict) and isinstance(value.get("value"), str):
                value["value"] = _scrub_text(value["value"])

    breadcrumbs = event.get("breadcrumbs")
    if isinstance(breadcrumbs, dict):
        for crumb in breadcrumbs.get("values", []):
            if isinstance(crumb, dict) and isinstance(crumb.get("message"), str):
                crumb["message"] = _scrub_text(crumb["message"])

    return event
