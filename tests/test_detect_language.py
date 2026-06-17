from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from document_translator.detect.language import detect_language
from document_translator.lib.llm import MockLLMClient

try:
    from langdetect import LangDetectException
except ImportError:
    LangDetectException = Exception  # type: ignore[misc, assignment]


SPANISH_SAMPLE = """
POR CUANTO las partes convienen mutuamente en celebrar el presente contrato de compraventa.
El Vendedor entregará la mercancía dentro de los treinta días siguientes a la firma del acuerdo.
El Comprador podrá rescindir el contrato mediante notificación escrita con diez días de anticipación.
La indemnización cubrirá toda responsabilidad derivada del incumplimiento del presente acuerdo contractual.
Las partes acuerdan someterse a la jurisdicción de los tribunales competentes de esta ciudad.
"""


def test_detect_language_spanish_high_confidence() -> None:
    lang, confidence, used_ai = detect_language(SPANISH_SAMPLE)
    assert lang == "es"
    assert confidence >= 0.85
    assert used_ai is False


def test_detect_language_short_text_ai_fallback() -> None:
    mock = MockLLMClient()
    mock.set_response("Hola", "fr")
    lang, confidence, used_ai = detect_language("Hola mundo contractual", llm=mock)
    assert lang == "fr"
    assert used_ai is True
    assert confidence == 0.5


def test_detect_language_short_text_no_llm() -> None:
    lang, confidence, used_ai = detect_language("tiny")
    assert lang == "unknown"
    assert confidence == 0.0
    assert used_ai is False


def test_detect_language_low_confidence_ai_fallback() -> None:
    mock = MockLLMClient()

    def return_de(system: str, user: str) -> str:
        if "language" in system.lower():
            return "de"
        return mock.prefix + user

    mock.complete = return_de  # type: ignore[method-assign]

    low_conf = MagicMock()
    low_conf.lang = "es"
    low_conf.prob = 0.4

    with patch("document_translator.detect.language.detect_langs", return_value=[low_conf]):
        lang, _confidence, used_ai = detect_language(SPANISH_SAMPLE, llm=mock, confidence_threshold=0.85)

    assert used_ai is True
    assert lang == "de"


def test_detect_language_exception_ai_fallback() -> None:
    mock = MockLLMClient()
    mock.set_response("partes", "it")

    with patch("document_translator.detect.language.detect_langs", side_effect=LangDetectException(0, "failed")):
        lang, confidence, used_ai = detect_language(SPANISH_SAMPLE, llm=mock)

    assert used_ai is True
    assert lang == "it"
    assert confidence == 0.5


def test_detect_language_no_llm_returns_top_lang() -> None:
    low_conf = MagicMock()
    low_conf.lang = "es"
    low_conf.prob = 0.4

    with patch("document_translator.detect.language.detect_langs", return_value=[low_conf]):
        lang, confidence, used_ai = detect_language(SPANISH_SAMPLE, llm=None, confidence_threshold=0.85)

    assert lang == "es"
    assert confidence == 0.4
    assert used_ai is False


def test_detect_language_empty_langs_ai_fallback() -> None:
    mock = MockLLMClient()
    mock.set_response("partes", "pt")

    with patch("document_translator.detect.language.detect_langs", return_value=[]):
        lang, confidence, used_ai = detect_language(SPANISH_SAMPLE, llm=mock)

    assert used_ai is True
    assert lang == "pt"
    assert confidence == 0.5


def test_detect_language_ai_strips_response() -> None:
    from document_translator.detect.ai import detect_language_ai

    mock = MockLLMClient()

    def return_french(system: str, user: str) -> str:
        return "FR\n"

    mock.complete = return_french  # type: ignore[method-assign]
    assert detect_language_ai(mock, "Hola mundo contractual de compraventa") == "fr"
