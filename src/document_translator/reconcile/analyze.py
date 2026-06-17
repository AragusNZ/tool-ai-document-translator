from __future__ import annotations

import json
import re

from rapidfuzz import fuzz

from document_translator.config.languages import lang_display_name
from document_translator.errors import IssueCode, IssueSeverity, PipelineIssue
from document_translator.lib.llm.protocol import LLMClient
from document_translator.models import DiscrepancySeverity
from document_translator.reconcile.compare import protected_tokens_differ
from document_translator.types import PipelineStage


def build_semantic_system(target_lang: str) -> str:
    language = lang_display_name(target_lang)
    return f"""You compare two {language} translations of the same source sentence.
Respond with JSON only: {{"equivalent": bool, "severity": "low"|"medium"|"high"|"breaking", "explanation": str}}
For legal documents, flag breaking severity when obligations, liability, scope, or negation differ."""


def build_adjudication_system(target_lang: str) -> str:
    language = lang_display_name(target_lang)
    return f"""You choose the best {language} translation from three variants of the same source text.
Respond with JSON only: {{"chosen": 1|2|3, "resolved_text": str, "rationale": str}}
Prefer fidelity to source meaning; for legal text, prefer the variant that preserves obligations precisely."""


def _parse_json_response(raw: str) -> tuple[dict[str, object] | None, PipelineIssue | None]:
    match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", raw)
    if not match:
        return None, PipelineIssue(
            code=IssueCode.LLM_RESPONSE_PARSE_FAILED,
            severity=IssueSeverity.WARN,
            message="Failed to parse AI response as JSON",
            stage=PipelineStage.RECONCILING,
        )
    try:
        return json.loads(match.group()), None
    except json.JSONDecodeError:
        return None, PipelineIssue(
            code=IssueCode.LLM_RESPONSE_PARSE_FAILED,
            severity=IssueSeverity.WARN,
            message="Invalid JSON from AI",
            stage=PipelineStage.RECONCILING,
        )


def analyze_semantic_equivalence(
    llm: LLMClient,
    *,
    translation_1: str,
    translation_2: str,
    context_before: str,
    context_after: str,
    is_legal: bool,
    target_lang: str = "en",
    document_summary: str = "",
    translation_context: str = "",
) -> tuple[dict[str, object], PipelineIssue | None]:
    context_lines: list[str] = []
    if translation_context.strip():
        context_lines.append(f"Translation context:\n{translation_context.strip()}")
    if document_summary.strip():
        context_lines.append(f"Document summary:\n{document_summary.strip()}")
    context_block = "\n\n".join(context_lines)
    if context_block:
        context_block += "\n\n"
    user = (
        f"Legal document: {is_legal}\n"
        f"{context_block}"
        f"Context before:\n{context_before}\n\n"
        f"Translation A:\n{translation_1}\n\n"
        f"Translation B:\n{translation_2}\n\n"
        f"Context after:\n{context_after}"
    )
    raw = llm.complete(build_semantic_system(target_lang), user)
    parsed, issue = _parse_json_response(raw)
    if parsed is None:
        return {"equivalent": False, "severity": "medium", "explanation": "Failed to parse AI response"}, issue
    return parsed, issue


def adjudicate_translations_ai(
    llm: LLMClient,
    *,
    variant_1: str,
    variant_2: str,
    variant_3: str,
    source_span: str,
    is_legal: bool,
    document_summary: str = "",
    translation_context: str = "",
    target_lang: str = "en",
) -> tuple[dict[str, object], PipelineIssue | None]:
    context_lines = []
    if translation_context.strip():
        context_lines.append(f"Translation context:\n{translation_context.strip()}")
    if document_summary.strip():
        context_lines.append(f"Document summary:\n{document_summary.strip()}")
    context_block = "\n\n".join(context_lines)
    if context_block:
        context_block += "\n\n"
    user = (
        f"Legal document: {is_legal}\n"
        f"{context_block}"
        f"Source span:\n{source_span}\n\n"
        f"Variant 1:\n{variant_1}\n\n"
        f"Variant 2:\n{variant_2}\n\n"
        f"Variant 3:\n{variant_3}"
    )
    raw = llm.complete(build_adjudication_system(target_lang), user)
    parsed, issue = _parse_json_response(raw)
    if parsed is None:
        return {"chosen": 1, "resolved_text": variant_1, "rationale": "Fallback to variant 1"}, issue
    return parsed, issue


def programmatic_pick_variant(
    variant_1: str,
    variant_2: str,
    variant_3: str,
) -> tuple[str, int, bool]:
    """Return (best_text, chosen_index, needs_ai_tiebreak)."""
    variants = [(1, variant_1), (2, variant_2), (3, variant_3)]
    scores: list[tuple[float, int, str]] = []
    for idx, text in variants:
        others = [t for j, t in variants if j != idx]
        avg = sum(fuzz.ratio(text, other) for other in others) / len(others)
        scores.append((avg, idx, text))
    scores.sort(key=lambda item: item[0], reverse=True)
    best_score, best_idx, best_text = scores[0]
    second_score = scores[1][0]
    token_conflict = any(
        protected_tokens_differ(best_text, t) for _, _, t in scores[1:]
    )
    needs_ai = (best_score - second_score) < 5.0 or token_conflict
    return best_text, best_idx, needs_ai


def severity_from_str(value: str) -> DiscrepancySeverity:
    try:
        return DiscrepancySeverity(value)
    except ValueError:
        return DiscrepancySeverity.MEDIUM


def pick_equivalent_translation(translation_1: str, translation_2: str) -> str:
    """When semantically equivalent, prefer the longer/more complete variant."""
    if len(translation_1) >= len(translation_2):
        return translation_1
    return translation_2
