from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from document_translator.config.defaults import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_TARGET_LANG,
    DOCUMENT_SUMMARY_MAX_CHARS,
    LANGUAGE_SAMPLE_MAX_CHARS,
    TRANSLATION_CONTEXT_MAX_CHARS,
)
from document_translator.config.languages import lang_display_name
from document_translator.errors import IssueCode, PipelineError
from document_translator.lib.job_control import JobDeadline
from document_translator.lib.llm.protocol import LLMClient
from document_translator.lib.text.chunker import TextChunk, chunk_document, reassemble_chunks
from document_translator.translate.glossary import Glossary
from document_translator.types import PipelineStage


def build_translation_system(target_lang: str, *, glossary: Glossary | None = None) -> str:
    language = lang_display_name(target_lang)
    glossary_note = ""
    if glossary and len(glossary) > 0:
        glossary_note = (
            " Honor glossary terms exactly: keep do-not-translate terms unchanged "
            "and use preferred translations when provided."
        )
    return f"""You are a professional document translator.
Translate the user's text faithfully into {language} ({target_lang}).
Preserve markdown structure: headings, lists, numbering, and paragraph breaks.
For legal text, preserve modal verbs (shall/may/must), party names, dates, currency, and amounts exactly.{glossary_note}
Return ONLY the translated markdown chunk with no commentary or preamble."""


def build_document_summary(text: str, *, max_chars: int = DOCUMENT_SUMMARY_MAX_CHARS) -> str:
    chunks = chunk_document(text, max_chars=LANGUAGE_SAMPLE_MAX_CHARS, overlap_sentences=0)
    if not chunks:
        return text[:max_chars]
    parts = [chunks[0].text[:250]]
    if len(chunks) > 1:
        parts.append(chunks[-1].text[:250])
    summary = "\n...\n".join(parts)
    return summary[:max_chars]


def normalize_translation_context(
    value: str | None,
    *,
    max_chars: int = TRANSLATION_CONTEXT_MAX_CHARS,
) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return stripped[:max_chars]


def _build_context_sections(
    *,
    document_summary: str = "",
    translation_context: str = "",
    section_context: str = "",
    glossary: Glossary | None = None,
) -> str:
    parts: list[str] = []
    if translation_context.strip():
        parts.append(f"Translation context:\n{translation_context.strip()}")
    if glossary is not None:
        glossary_block = glossary.format_for_prompt()
        if glossary_block:
            parts.append(glossary_block)
    if document_summary.strip():
        parts.append(f"Document summary:\n{document_summary.strip()}")
    if section_context.strip():
        parts.append(f"Section context: {section_context.strip()}")
    if not parts:
        return ""
    return "\n".join(parts) + "\n\n"


def build_third_pass_prompt(
    *,
    source_chunk: TextChunk,
    source_span: str,
    source_lang: str,
    target_lang: str,
    is_legal: bool,
    document_summary: str,
    translation_context: str = "",
    section_context: str = "",
    glossary: Glossary | None = None,
) -> str:
    legal_note = " This is a legal document — preserve obligations and defined terms precisely." if is_legal else ""
    target_language = lang_display_name(target_lang)
    context_block = _build_context_sections(
        document_summary=document_summary,
        translation_context=translation_context,
        section_context=section_context or source_chunk.heading_context,
        glossary=glossary,
    )
    return (
        f"Source language: {source_lang}. Target language: {target_language} ({target_lang}).{legal_note}\n"
        f"{context_block}"
        f"Translate this span:\n\n{source_span}"
    )


def _build_user_prompt(
    chunk: TextChunk,
    source_lang: str,
    target_lang: str,
    is_legal: bool,
    *,
    document_summary: str = "",
    translation_context: str = "",
    glossary: Glossary | None = None,
) -> str:
    legal_note = " This is a legal document — preserve obligations and defined terms precisely." if is_legal else ""
    target_language = lang_display_name(target_lang)
    context_block = _build_context_sections(
        document_summary=document_summary,
        translation_context=translation_context,
        section_context=chunk.heading_context,
        glossary=glossary,
    )
    return (
        f"Source language: {source_lang}. Target language: {target_language} ({target_lang}).{legal_note}\n"
        f"{context_block}"
        f"Chunk {chunk.index + 1}\n\n"
        f"{chunk.text}"
    )


def translate_chunks(
    llm: LLMClient,
    chunks: list[TextChunk],
    *,
    source_lang: str,
    target_lang: str = DEFAULT_TARGET_LANG,
    is_legal: bool = False,
    document_summary: str = "",
    translation_context: str = "",
    glossary: Glossary | None = None,
    max_workers: int = 4,
    deadline: JobDeadline | None = None,
    completed_chunks: dict[int, str] | None = None,
    on_chunk_complete: Callable[[int, str], None] | None = None,
) -> list[str]:
    results: dict[int, str] = dict(completed_chunks or {})
    system_prompt = build_translation_system(target_lang, glossary=glossary)
    pending = [chunk for chunk in chunks if chunk.index not in results]

    def translate_one(chunk: TextChunk) -> tuple[int, str]:
        translated = llm.complete(
            system_prompt,
            _build_user_prompt(
                chunk,
                source_lang,
                target_lang,
                is_legal,
                document_summary=document_summary,
                translation_context=translation_context,
                glossary=glossary,
            ),
        )
        return chunk.index, translated.strip()

    if not pending:
        return [results[i] for i in range(len(chunks))]

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(translate_one, c): c.index for c in pending}
        for future in as_completed(futures):
            if deadline is not None:
                deadline.check(PipelineStage.TRANSLATING)
            chunk_idx = futures[future]
            try:
                idx, text = future.result()
            except Exception as exc:
                raise PipelineError(
                    f"Translation failed for chunk {chunk_idx}: {exc}",
                    code=IssueCode.PIPELINE_FAILED,
                    stage=PipelineStage.TRANSLATING,
                    cause=exc,
                    scope={"chunk_index": str(chunk_idx)},
                ) from exc
            results[idx] = text
            if on_chunk_complete is not None:
                on_chunk_complete(idx, text)

    return [results[i] for i in range(len(chunks))]


def translate_document(
    llm: LLMClient,
    text: str,
    *,
    source_lang: str,
    target_lang: str = DEFAULT_TARGET_LANG,
    is_legal: bool = False,
    document_summary: str = "",
    translation_context: str = "",
    glossary: Glossary | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap_sentences: int = DEFAULT_CHUNK_OVERLAP,
    max_workers: int = 4,
) -> tuple[str, int]:
    chunks = chunk_document(text, max_chars=chunk_size, overlap_sentences=overlap_sentences)
    translated = translate_chunks(
        llm,
        chunks,
        source_lang=source_lang,
        target_lang=target_lang,
        is_legal=is_legal,
        document_summary=document_summary,
        translation_context=translation_context,
        glossary=glossary,
        max_workers=max_workers,
    )
    return reassemble_chunks(translated), len(chunks)


def translate_source_chunks(
    llm: LLMClient,
    source_chunks: list[TextChunk],
    *,
    source_lang: str,
    target_lang: str = DEFAULT_TARGET_LANG,
    is_legal: bool = False,
    document_summary: str = "",
    translation_context: str = "",
    glossary: Glossary | None = None,
    max_workers: int = 4,
    deadline: JobDeadline | None = None,
    completed_chunks: dict[int, str] | None = None,
    on_chunk_complete: Callable[[int, str], None] | None = None,
) -> list[str]:
    return translate_chunks(
        llm,
        source_chunks,
        source_lang=source_lang,
        target_lang=target_lang,
        is_legal=is_legal,
        document_summary=document_summary,
        translation_context=translation_context,
        glossary=glossary,
        max_workers=max_workers,
        deadline=deadline,
        completed_chunks=completed_chunks,
        on_chunk_complete=on_chunk_complete,
    )
