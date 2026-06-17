from __future__ import annotations

import json
from pathlib import Path

from document_translator.errors import ChunkCountMismatchError, IssueCode, PipelineError
from document_translator.types import PipelineStage
from document_translator.models import Discrepancy, DiscrepancySeverity
from document_translator.report.collector import IssueCollector
from document_translator.reconcile.analyze import (
    adjudicate_translations_ai,
    analyze_semantic_equivalence,
    pick_equivalent_translation,
    programmatic_pick_variant,
    severity_from_str,
)
from document_translator.reconcile.compare import compare_chunk_pair, split_sentences
from document_translator.config.defaults import DEFAULT_SIMILARITY_THRESHOLD, DEFAULT_TARGET_LANG
from document_translator.lib.llm.protocol import LLMClient
from document_translator.lib.job_control import JobDeadline
from document_translator.lib.text.chunker import TextChunk, reassemble_chunks
from document_translator.translate.service import build_third_pass_prompt, build_translation_system


def reconcile_translations(
    llm: LLMClient,
    *,
    source_chunks: list[TextChunk],
    translation_1_chunks: list[str],
    translation_2_chunks: list[str],
    source_lang: str,
    target_lang: str = DEFAULT_TARGET_LANG,
    is_legal: bool,
    document_summary: str = "",
    translation_context: str = "",
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    collector: IssueCollector | None = None,
    deadline: JobDeadline | None = None,
) -> tuple[str, list[Discrepancy]]:
    if len(translation_1_chunks) != len(translation_2_chunks):
        raise ChunkCountMismatchError(len(translation_1_chunks), len(translation_2_chunks))
    if len(translation_1_chunks) != len(source_chunks):
        raise PipelineError(
            f"Source/translation chunk count mismatch: source={len(source_chunks)}, "
            f"translations={len(translation_1_chunks)}",
            code=IssueCode.CHUNK_COUNT_MISMATCH,
            stage=PipelineStage.RECONCILING,
            scope={"source": str(len(source_chunks)), "translations": str(len(translation_1_chunks))},
        )

    resolved_chunks: list[str] = []
    discrepancies: list[Discrepancy] = []

    for chunk_idx, source_chunk in enumerate(source_chunks):
        if deadline is not None:
            deadline.check(PipelineStage.RECONCILING)
        t1 = translation_1_chunks[chunk_idx]
        t2 = translation_2_chunks[chunk_idx]
        src_text = source_chunk.text

        flagged = compare_chunk_pair(t1, t2, similarity_threshold=similarity_threshold)
        if not flagged:
            resolved_chunks.append(t1 or t2)
            continue

        sentences_1 = split_sentences(t1)
        sentences_2 = split_sentences(t2)
        resolved_sentences = sentences_1[:] if len(sentences_1) >= len(sentences_2) else sentences_2[:]

        for item in flagged:
            idx = int(item["sentence_index"])
            s1 = str(item["translation_1"])
            s2 = str(item["translation_2"])
            before = " ".join(sentences_1[max(0, idx - 2) : idx])
            after = " ".join(sentences_1[idx + 1 : idx + 3])

            analysis, parse_issue = analyze_semantic_equivalence(
                llm,
                translation_1=s1,
                translation_2=s2,
                context_before=before,
                context_after=after,
                is_legal=is_legal,
                target_lang=target_lang,
                document_summary=document_summary,
                translation_context=translation_context,
            )
            if parse_issue and collector:
                collector.extend([parse_issue])
            equivalent = bool(analysis.get("equivalent"))
            severity = severity_from_str(str(analysis.get("severity", "medium")))
            explanation = str(analysis.get("explanation", ""))

            source_span = ""
            src_sentences = split_sentences(src_text)
            if idx < len(src_sentences):
                source_span = src_sentences[idx]

            disc = Discrepancy(
                chunk_index=chunk_idx,
                sentence_index=idx,
                translation_1=s1,
                translation_2=s2,
                source_span=source_span,
                equivalent=equivalent,
                severity=severity,
                explanation=explanation,
            )

            if equivalent:
                disc.resolved = True
                disc.resolution = pick_equivalent_translation(s1, s2)
                disc.chosen_variant = disc.resolution
                if idx < len(resolved_sentences):
                    resolved_sentences[idx] = disc.resolution
            else:
                variant_3 = llm.complete(
                    build_translation_system(target_lang),
                    build_third_pass_prompt(
                        source_chunk=source_chunk,
                        source_span=source_span or src_text,
                        source_lang=source_lang,
                        target_lang=target_lang,
                        is_legal=is_legal,
                        document_summary=document_summary,
                        translation_context=translation_context,
                        section_context=source_chunk.heading_context,
                    ),
                )
                prog_text, prog_idx, needs_ai = programmatic_pick_variant(s1, s2, variant_3)
                if needs_ai or severity == DiscrepancySeverity.BREAKING:
                    adjudication, adj_issue = adjudicate_translations_ai(
                        llm,
                        variant_1=s1,
                        variant_2=s2,
                        variant_3=variant_3,
                        source_span=source_span or src_text,
                        is_legal=is_legal,
                        document_summary=document_summary,
                        translation_context=translation_context,
                        target_lang=target_lang,
                    )
                    if adj_issue and collector:
                        collector.extend([adj_issue])
                    resolved_text = str(adjudication.get("resolved_text", prog_text))
                    rationale = str(adjudication.get("rationale", ""))
                else:
                    resolved_text = prog_text
                    rationale = f"programmatic consensus (variant {prog_idx})"

                disc.resolved = True
                disc.resolution = resolved_text
                disc.chosen_variant = resolved_text
                disc.explanation = f"{explanation}; {rationale}".strip("; ")
                if idx < len(resolved_sentences):
                    resolved_sentences[idx] = resolved_text
                elif resolved_sentences:
                    resolved_sentences.append(resolved_text)
                else:
                    resolved_sentences = [resolved_text]

            discrepancies.append(disc)

        resolved_chunks.append(
            _join_sentences(resolved_sentences) if resolved_sentences else (t1 or t2)
        )

    return reassemble_chunks(resolved_chunks), discrepancies


def _join_sentences(sentences: list[str]) -> str:
    return " ".join(s.strip() for s in sentences if s.strip())


def write_discrepancies(path: Path, discrepancies: list[Discrepancy]) -> None:
    payload = [d.model_dump(mode="json") for d in discrepancies]
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
