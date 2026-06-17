from document_translator.reconcile.analyze import (
    adjudicate_translations_ai,
    analyze_semantic_equivalence,
    build_adjudication_system,
    build_semantic_system,
    pick_equivalent_translation,
    programmatic_pick_variant,
    severity_from_str,
)
from document_translator.models import DiscrepancySeverity
from document_translator.lib.llm import MockLLMClient


def test_programmatic_pick_variant() -> None:
    v1 = "The party shall pay within 30 days."
    v2 = "The party shall pay within 30 days."
    v3 = "The party may pay within 30 days."
    text, idx, needs_ai = programmatic_pick_variant(v1, v2, v3)
    assert idx in (1, 2)
    assert "shall" in text
    assert needs_ai is True


def test_severity_from_str() -> None:
    assert severity_from_str("high") == DiscrepancySeverity.HIGH
    assert severity_from_str("not-a-severity") == DiscrepancySeverity.MEDIUM


def test_analyze_semantic_equivalence_includes_context() -> None:
    mock = MockLLMClient()
    analyze_semantic_equivalence(
        mock,
        translation_1="A",
        translation_2="B",
        context_before="before",
        context_after="after",
        is_legal=False,
        document_summary="Summary text.",
        translation_context="Contract between X and Y.",
    )
    _system, user = mock.calls[-1]
    assert "Document summary:" in user
    assert "Translation context:" in user
    assert "Contract between X and Y." in user


def test_analyze_semantic_equivalence_valid_json() -> None:
    mock = MockLLMClient()
    mock.set_response("Translation A", '{"equivalent": true, "severity": "low", "explanation": "same"}')
    result, issue = analyze_semantic_equivalence(
        mock,
        translation_1="The party shall pay.",
        translation_2="The party shall pay.",
        context_before="",
        context_after="",
        is_legal=True,
    )
    assert result["equivalent"] is True
    assert issue is None


def test_analyze_semantic_equivalence_invalid_json() -> None:
    mock = MockLLMClient()
    mock.set_response("Translation A", "not json")
    result, issue = analyze_semantic_equivalence(
        mock,
        translation_1="A",
        translation_2="B",
        context_before="",
        context_after="",
        is_legal=False,
    )
    assert result["equivalent"] is False
    assert issue is not None
    assert issue.code.value == "LLM_RESPONSE_PARSE_FAILED"


def test_adjudicate_translations_ai_valid_json() -> None:
    mock = MockLLMClient()
    mock.set_response(
        "Variant 1",
        '{"chosen": 2, "resolved_text": "Resolved text.", "rationale": "best fit"}',
    )
    result, issue = adjudicate_translations_ai(
        mock,
        variant_1="Variant one.",
        variant_2="Variant two.",
        variant_3="Variant three.",
        source_span="Source.",
        is_legal=False,
    )
    assert result["chosen"] == 2
    assert result["resolved_text"] == "Resolved text."
    assert issue is None


def test_adjudicate_translations_ai_invalid_json_fallback() -> None:
    mock = MockLLMClient()
    mock.set_response("Variant 1", "garbage")
    result, issue = adjudicate_translations_ai(
        mock,
        variant_1="First variant.",
        variant_2="Second variant.",
        variant_3="Third variant.",
        source_span="Source.",
        is_legal=False,
    )
    assert result["chosen"] == 1
    assert result["resolved_text"] == "First variant."
    assert issue is not None


def test_pick_equivalent_translation() -> None:
    assert pick_equivalent_translation("Short.", "A longer translation.") == "A longer translation."
    assert pick_equivalent_translation("Longer text here.", "Short.") == "Longer text here."


def test_build_semantic_system_uses_target_language() -> None:
    system = build_semantic_system("fr")
    assert "French" in system
    assert "translations" in system


def test_build_adjudication_system_uses_target_language() -> None:
    system = build_adjudication_system("de")
    assert "German" in system
