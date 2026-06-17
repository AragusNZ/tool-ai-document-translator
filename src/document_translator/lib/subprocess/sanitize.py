from __future__ import annotations

import re

_MAX_DETAIL_LEN = 500
_PATH_RE = re.compile(r"(?:/[A-Za-z0-9_.@+-]+){2,}|(?:[A-Za-z]:\\)[^\s]+")


def sanitize_subprocess_detail(detail: str) -> str:
    cleaned = detail.strip()
    cleaned = _PATH_RE.sub("<path>", cleaned)
    if len(cleaned) > _MAX_DETAIL_LEN:
        return cleaned[:_MAX_DETAIL_LEN] + "..."
    return cleaned
