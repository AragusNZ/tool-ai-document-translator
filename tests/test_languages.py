from __future__ import annotations

from pathlib import Path

import pytest

from document_translator.config.languages import is_rtl_lang, normalize_lang_code
from document_translator.export.pdf import resolve_pdf_css_path, rtl_css_path


def test_is_rtl_lang() -> None:
    assert is_rtl_lang("ar")
    assert is_rtl_lang("he")
    assert not is_rtl_lang("en")
    assert normalize_lang_code("AR") == "ar"


def test_resolve_pdf_css_path() -> None:
    assert resolve_pdf_css_path(rtl=False).name == "translation.css"
    assert resolve_pdf_css_path(rtl=True).name == "translation-rtl.css"
    assert rtl_css_path().exists()
