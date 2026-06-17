from __future__ import annotations

import pytest

from document_translator.config.languages import lang_display_name, normalize_lang_code


def test_normalize_lang_code_lowercases() -> None:
    assert normalize_lang_code("ES") == "es"
    assert normalize_lang_code("  fr  ") == "fr"


def test_normalize_lang_code_rejects_invalid() -> None:
    with pytest.raises(ValueError, match="Invalid language code"):
        normalize_lang_code("eng")
    with pytest.raises(ValueError, match="Invalid language code"):
        normalize_lang_code("e")
    with pytest.raises(ValueError, match="Invalid language code"):
        normalize_lang_code("")


def test_lang_display_name_known_codes() -> None:
    assert lang_display_name("en") == "English"
    assert lang_display_name("es") == "Spanish"


def test_lang_display_name_unknown_code_falls_back() -> None:
    assert lang_display_name("xx") == "xx"


def test_supported_language_codes_matches_display_names() -> None:
    from document_translator.config.languages import SUPPORTED_LANGUAGE_CODES

    assert "en" in SUPPORTED_LANGUAGE_CODES
    assert "es" in SUPPORTED_LANGUAGE_CODES
    assert len(SUPPORTED_LANGUAGE_CODES) == 15
