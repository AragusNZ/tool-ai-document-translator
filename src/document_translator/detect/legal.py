from __future__ import annotations

import json
import re

from document_translator.config.defaults import LEGAL_KEYWORDS
from document_translator.lib.llm.protocol import LLMClient

LEGAL_CONFIRM_SYSTEM = """Is this document primarily a legal contract, agreement, or similar legal instrument?
Respond with JSON only: {"is_legal": bool, "confidence": float}"""


def count_legal_keywords(text: str) -> int:
    lower = text.lower()
    return sum(1 for pattern in LEGAL_KEYWORDS if re.search(pattern, lower))


def is_legal_document(text: str) -> bool:
    return count_legal_keywords(text) >= 3


def classify_legal_document(text: str, llm: LLMClient | None = None) -> tuple[bool, bool, bool]:
    """Return (is_legal, used_ai_confirm, ai_parse_failed)."""
    hits = count_legal_keywords(text)
    if hits >= 3:
        return True, False, False
    if hits == 0:
        return False, False, False
    if llm is None:
        return hits >= 2, False, False

    sample = text[:4000]
    raw = llm.complete(LEGAL_CONFIRM_SYSTEM, sample)
    match = re.search(r"\{[^{}]*\}", raw)
    if not match:
        return hits >= 2, True, True
    try:
        payload = json.loads(match.group())
        return bool(payload.get("is_legal")), True, False
    except json.JSONDecodeError:
        return hits >= 2, True, True
