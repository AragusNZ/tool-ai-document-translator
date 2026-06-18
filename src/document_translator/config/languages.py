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
    "he": "Hebrew",
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

RTL_LANGUAGE_CODES: frozenset[str] = frozenset({"ar", "he"})


def is_rtl_lang(code: str) -> bool:
    return normalize_lang_code(code) in RTL_LANGUAGE_CODES


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
    "RTL_LANGUAGE_CODES",
    "SUPPORTED_LANGUAGE_CODES",
    "is_rtl_lang",
    "lang_display_name",
    "normalize_lang_code",
]
