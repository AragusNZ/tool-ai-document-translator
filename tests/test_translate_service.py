from __future__ import annotations

import pytest

from document_translator.errors import IssueCode, PipelineError
from document_translator.lib.llm import MockLLMClient
from document_translator.lib.text.chunker import TextChunk, chunk_document
from document_translator.translate.service import (
    build_document_summary,
    build_third_pass_prompt,
    build_translation_system,
    normalize_translation_context,
    translate_chunks,
)


def test_build_document_summary_truncates() -> None:
    text = "Intro paragraph.\n\n" + ("Word " * 500)
    summary = build_document_summary(text, max_chars=100)
    assert len(summary) <= 100


def test_build_third_pass_prompt_legal_note() -> None:
    chunk = TextChunk(index=0, text="Span text.", heading_context="# Section")
    prompt = build_third_pass_prompt(
        source_chunk=chunk,
        source_span="Span text.",
        source_lang="es",
        target_lang="en",
        is_legal=True,
        document_summary="Summary.",
    )
    assert "legal document" in prompt.lower()
    assert "Section" in prompt


def test_build_third_pass_prompt_no_legal_note() -> None:
    chunk = TextChunk(index=0, text="Span text.", heading_context="")
    prompt = build_third_pass_prompt(
        source_chunk=chunk,
        source_span="Span text.",
        source_lang="fr",
        target_lang="en",
        is_legal=False,
        document_summary="Summary.",
    )
    assert "legal document" not in prompt.lower()


def test_build_third_pass_prompt_includes_translation_context() -> None:
    chunk = TextChunk(index=0, text="Span text.", heading_context="# Section")
    prompt = build_third_pass_prompt(
        source_chunk=chunk,
        source_span="Span text.",
        source_lang="es",
        target_lang="en",
        is_legal=False,
        document_summary="Summary.",
        translation_context="Contract between Acme and Beta Corp.",
    )
    assert "Translation context:" in prompt
    assert "Acme and Beta Corp" in prompt
    assert "Document summary:" in prompt


def test_normalize_translation_context_strips_and_truncates() -> None:
    assert normalize_translation_context("  hello  ") == "hello"
    assert normalize_translation_context("   ") is None
    assert normalize_translation_context(None) is None
    long_text = "x" * 3000
    assert len(normalize_translation_context(long_text) or "") == 2000


def test_translate_chunks_includes_context_in_prompt() -> None:
    mock = MockLLMClient(prefix="[EN] ")
    chunks = [TextChunk(index=0, text="Hello world.", heading_context="")]
    translate_chunks(
        mock,
        chunks,
        source_lang="es",
        target_lang="en",
        document_summary="Opening clause.",
        translation_context="This is a contract between X and Y.",
        max_workers=1,
    )
    _system, user = mock.calls[-1]
    assert "Document summary:" in user
    assert "Opening clause." in user
    assert "Translation context:" in user
    assert "contract between X and Y" in user


def test_translate_chunks_calls_llm_per_chunk() -> None:
    mock = MockLLMClient(prefix="[EN] ")
    text = "First paragraph.\n\n" + ("Sentence. " * 200)
    chunks = chunk_document(text, max_chars=500, overlap_sentences=0)
    results = translate_chunks(
        mock, chunks, source_lang="es", target_lang="en", is_legal=False, max_workers=1
    )
    assert len(results) == len(chunks)
    assert mock.tracker.count >= len(chunks)


def test_translate_chunks_raises_pipeline_error() -> None:
    mock = MockLLMClient()

    def fail(system: str, user: str) -> str:
        if "Chunk" in user:
            raise RuntimeError("LLM down")
        return "ok"

    mock.complete = fail  # type: ignore[method-assign]
    chunks = [TextChunk(index=0, text="Hello world.", heading_context="")]

    with pytest.raises(PipelineError) as exc_info:
        translate_chunks(mock, chunks, source_lang="es")

    assert exc_info.value.code == IssueCode.PIPELINE_FAILED


def test_build_translation_system_includes_target_language() -> None:
    system = build_translation_system("fr")
    assert "French" in system
    assert "(fr)" in system


def test_translate_chunks_uses_target_language_in_prompt() -> None:
    mock = MockLLMClient(prefix="[FR] ")
    chunks = [TextChunk(index=0, text="Hello world.", heading_context="")]
    translate_chunks(mock, chunks, source_lang="en", target_lang="fr", max_workers=1)
    assert mock.tracker.count == 1
    assert mock.calls
    _system, user = mock.calls[-1]
    assert "French" in user
    assert "Target language" in user
