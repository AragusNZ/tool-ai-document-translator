from __future__ import annotations

import re

from document_translator.config.defaults import DEFAULT_TARGET_LANG

_LANG_CODE_RE = re.compile(r"^[a-z]{2}$")

_DISPLAY_NAMES: dict[str, str] = {
    "ar": "Arabic",
    "de": "German",
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "it": "Italian",
    "ja": "Japanese",
    "ko": "Korean",
    "nl": "Dutch",
    "pl": "Polish",
    "pt": "Portuguese",
    "ru": "Russian",
    "sv": "Swedish",
    "tr": "Turkish",
    "zh": "Chinese",
}

SUPPORTED_LANGUAGE_CODES: frozenset[str] = frozenset(_DISPLAY_NAMES)


def normalize_lang_code(code: str) -> str:
    normalized = code.strip().lower()
    if not _LANG_CODE_RE.match(normalized):
        raise ValueError(f"Invalid language code: {code!r} (expected ISO 639-1, e.g. en, es, fr)")
    return normalized


def lang_display_name(code: str) -> str:
    normalized = normalize_lang_code(code)
    return _DISPLAY_NAMES.get(normalized, normalized)


__all__ = [
    "DEFAULT_TARGET_LANG",
    "SUPPORTED_LANGUAGE_CODES",
    "lang_display_name",
    "normalize_lang_code",
]
