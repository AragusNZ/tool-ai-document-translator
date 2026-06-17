from __future__ import annotations

_CHARS_PER_TOKEN = 4


def estimate_tokens_from_text(text: str) -> int:
    stripped = text.strip()
    if not stripped:
        return 0
    return max(1, (len(stripped) + _CHARS_PER_TOKEN - 1) // _CHARS_PER_TOKEN)
