from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from document_translator.errors import ChunkCountMismatchError, IssueCode, PipelineError
from document_translator.lib.llm import MockLLMClient
from document_translator.lib.text.chunker import TextChunk
from document_translator.models import Discrepancy
from document_translator.reconcile.resolve import reconcile_translations, write_discrepancies


def _source_chunks() -> list[TextChunk]:
    return [TextChunk(index=0, text="The party shall pay within 30 days.", heading_context="")]


def test_reconcile_identical_passes_no_discrepancies() -> None:
    mock = MockLLMClient(prefix="[EN] ")
    text = "The party shall pay within 30 days."
    resolved, discrepancies = reconcile_translations(
        mock,
        source_chunks=_source_chunks(),
        translation_1_chunks=[text],
        translation_2_chunks=[text],
        source_lang="es",
        is_legal=True,
    )
    assert resolved.strip() == text
    assert discrepancies == []


def test_reconcile_divergent_sentences_with_mock() -> None:
    mock = MockLLMClient(prefix="[EN] ")

    def responses(system: str, user: str) -> str:
        if "equivalent" in system.lower():
            return '{"equivalent": false, "severity": "high", "explanation": "modal differs"}'
        if "adjudicate" in system.lower() or "choose" in system.lower():
            return json.dumps(
                {"chosen": 1, "resolved_text": "The party shall pay within 30 days.", "rationale": "legal"}
            )
        return "[EN] The party shall pay within 30 days."

    mock.complete = responses  # type: ignore[method-assign]

    t1 = "The party shall pay within 30 days."
    t2 = "The party may pay within 30 days."
    resolved, discrepancies = reconcile_translations(
        mock,
        source_chunks=_source_chunks(),
        translation_1_chunks=[t1],
        translation_2_chunks=[t2],
        source_lang="es",
        is_legal=True,
    )
    assert discrepancies
    assert discrepancies[0].resolved is True
    assert "shall" in resolved


def test_reconcile_semantically_equivalent_resolves_without_adjudication() -> None:
    mock = MockLLMClient(prefix="[EN] ")

    def responses(system: str, user: str) -> str:
        if "equivalent" in system.lower():
            return '{"equivalent": true, "severity": "low", "explanation": "same meaning"}'
        return "[EN] The party shall pay within 30 days."

    mock.complete = responses  # type: ignore[method-assign]

    t1 = "The party shall pay within 30 days."
    t2 = "The party may pay within 30 days."
    resolved, discrepancies = reconcile_translations(
        mock,
        source_chunks=_source_chunks(),
        translation_1_chunks=[t1],
        translation_2_chunks=[t2],
        source_lang="es",
        is_legal=True,
    )
    assert len(discrepancies) == 1
    assert discrepancies[0].equivalent is True
    assert discrepancies[0].resolved is True
    assert "shall" in resolved


def test_reconcile_programmatic_consensus_without_adjudication() -> None:
    mock = MockLLMClient(prefix="[EN] ")
    consensus = "The vendor shall deliver goods."

    def responses(system: str, user: str) -> str:
        if "equivalent" in system.lower():
            return '{"equivalent": false, "severity": "medium", "explanation": "minor wording"}'
        return consensus

    mock.complete = responses  # type: ignore[method-assign]

    t1 = consensus
    t2 = "The vendor shall deliver merchandise."
    with patch(
        "document_translator.reconcile.resolve.programmatic_pick_variant",
        return_value=(consensus, 1, False),
    ):
        resolved, discrepancies = reconcile_translations(
            mock,
            source_chunks=[TextChunk(index=0, text="El vendedor entregará mercancías.", heading_context="")],
            translation_1_chunks=[t1],
            translation_2_chunks=[t2],
            source_lang="es",
            is_legal=False,
            similarity_threshold=100.0,
        )
    assert discrepancies
    assert discrepancies[0].resolved is True
    assert "programmatic consensus" in discrepancies[0].explanation
    assert consensus in resolved


def test_reconcile_chunk_count_mismatch() -> None:
    mock = MockLLMClient()
    with pytest.raises(ChunkCountMismatchError) as exc_info:
        reconcile_translations(
            mock,
            source_chunks=_source_chunks(),
            translation_1_chunks=["a"],
            translation_2_chunks=["a", "b"],
            source_lang="es",
            is_legal=False,
        )
    assert exc_info.value.code == IssueCode.CHUNK_COUNT_MISMATCH


def test_reconcile_source_chunk_mismatch() -> None:
    mock = MockLLMClient()
    with pytest.raises(PipelineError) as exc_info:
        reconcile_translations(
            mock,
            source_chunks=_source_chunks(),
            translation_1_chunks=["a", "b"],
            translation_2_chunks=["a", "b"],
            source_lang="es",
            is_legal=False,
        )
    assert exc_info.value.code == IssueCode.CHUNK_COUNT_MISMATCH


def test_write_discrepancies_round_trip(tmp_path: Path) -> None:
    disc = Discrepancy(
        chunk_index=0,
        sentence_index=0,
        translation_1="A",
        translation_2="B",
        severity="low",
        resolved=True,
        resolution="A",
    )
    path = tmp_path / "discrepancies.json"
    write_discrepancies(path, [disc])
    payload = json.loads(path.read_text())
    assert payload[0]["translation_1"] == "A"
    assert payload[0]["resolved"] is True
