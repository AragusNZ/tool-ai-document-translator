from __future__ import annotations

import json

from document_translator.detect.legal import (
    classify_legal_document,
    count_legal_keywords,
    is_legal_document,
)
from document_translator.lib.llm import MockLLMClient


def test_count_legal_keywords_tiers() -> None:
    assert count_legal_keywords("Hello world.") == 0
    assert count_legal_keywords("The party shall pay.") == 2
    assert count_legal_keywords(
        "WHEREAS the parties shall indemnify liability under this agreement."
    ) >= 3


def test_is_legal_document_clear_legal() -> None:
    assert is_legal_document("WHEREAS the parties shall indemnify liability under this agreement.")


def test_classify_legal_document_clear_legal_no_ai() -> None:
    text = "WHEREAS the parties shall indemnify liability under this agreement and contract."
    is_legal, used_ai, parse_failed = classify_legal_document(text)
    assert is_legal is True
    assert used_ai is False
    assert parse_failed is False


def test_classify_legal_document_zero_hits() -> None:
    is_legal, used_ai, parse_failed = classify_legal_document("Hello world, this is a casual note.")
    assert is_legal is False
    assert used_ai is False
    assert parse_failed is False


def test_classify_legal_document_ambiguous_with_llm() -> None:
    mock = MockLLMClient()
    mock.set_response("party", json.dumps({"is_legal": True, "confidence": 0.9}))
    text = "The party shall deliver goods by Friday."
    is_legal, used_ai, parse_failed = classify_legal_document(text, mock)
    assert is_legal is True
    assert used_ai is True
    assert parse_failed is False


def test_classify_legal_document_invalid_llm_json_fallback() -> None:
    mock = MockLLMClient()
    mock.set_response("party", "not json at all")
    text = "The party shall deliver goods."
    is_legal, used_ai, parse_failed = classify_legal_document(text, mock)
    assert is_legal is True
    assert used_ai is True
    assert parse_failed is True


def test_classify_legal_document_no_llm_ambiguous() -> None:
    is_legal, used_ai, parse_failed = classify_legal_document("The party shall deliver goods.")
    assert is_legal is True
    assert used_ai is False
    assert parse_failed is False


def test_classify_legal_document_json_decode_error() -> None:
    mock = MockLLMClient()
    mock.set_response("party", '{"is_legal": true, "confidence":')
    text = "The party shall deliver goods."
    is_legal, used_ai, parse_failed = classify_legal_document(text, mock)
    assert is_legal is True
    assert used_ai is True
    assert parse_failed is True
