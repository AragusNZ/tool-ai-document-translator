from __future__ import annotations

import re

from document_translator.lib.llm.protocol import LLMClient

LANGUAGE_SYSTEM = """Identify the primary language of the text.
Respond with a single ISO 639-1 language code only (e.g. en, es, fr, de)."""


def detect_language_ai(llm: LLMClient, sample: str) -> str:
    code = llm.complete(LANGUAGE_SYSTEM, sample[:4000]).strip().lower()
    return re.sub(r"[^a-z]", "", code)[:2] or "unknown"
