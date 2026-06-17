from __future__ import annotations

from datetime import UTC, datetime

from document_translator.config.languages import lang_display_name
from document_translator.errors import IssueSeverity
from document_translator.lib.llm.protocol import LLMClient
from document_translator.models import Discrepancy, DiscrepancySeverity, JobMetadata, JobSummary
from document_translator.types import JobStatus, TranslationMode

_MAX_WARNINGS = 3
_MAX_REVIEW_ITEMS = 5


def build_cover_translation_system(target_lang: str) -> str:
    language = lang_display_name(target_lang)
    return f"""You are a professional translator.
Translate the cover page markdown into {language} ({target_lang}).
Preserve markdown structure: headings, bold labels, bullet lists, and inline code spans.
Keep job IDs, ISO 639-1 codes (e.g. en, es), model names, and filenames unchanged.
Return ONLY the translated markdown with no commentary or preamble."""


def translate_cover_markdown(
    llm: LLMClient,
    cover_md: str,
    *,
    target_lang: str,
) -> str:
    if target_lang == "en":
        return cover_md
    return llm.complete(
        build_cover_translation_system(target_lang),
        cover_md,
    ).strip()


def _outcome_headline(metadata: JobMetadata, *, has_warnings: bool) -> str:
    if metadata.job_status == JobStatus.FAILED:
        return "Translation did not complete successfully."
    if metadata.skipped_translation:
        target = lang_display_name(metadata.target_lang)
        return f"Document was already in {target}; text was passed through without translation."
    if has_warnings:
        return "Translation completed with warnings."
    return "Translation completed successfully."


def _user_warnings(metadata: JobMetadata) -> list[str]:
    messages: list[str] = []
    for issue in metadata.issues:
        if issue.severity in (IssueSeverity.WARN, IssueSeverity.ERROR):
            messages.append(issue.message)
        if len(messages) >= _MAX_WARNINGS:
            break
    for alert in metadata.extraction_alerts:
        if alert.severity == "warn":
            messages.append(alert.message)
        if len(messages) >= _MAX_WARNINGS:
            break
    return messages[:_MAX_WARNINGS]


def _review_items(discrepancies: list[Discrepancy]) -> list[str]:
    breaking = [
        d for d in discrepancies if d.severity == DiscrepancySeverity.BREAKING and not d.resolved
    ]
    display_count = _MAX_REVIEW_ITEMS - 1 if len(breaking) > _MAX_REVIEW_ITEMS - 1 else len(breaking)
    items = [
        d.explanation or "A significant translation difference may need your review."
        for d in breaking[:display_count]
    ]
    remaining = len(breaking) - display_count
    if remaining > 0:
        items.append(f"+ {remaining} more item(s) listed in the job metadata.")
    return items[:_MAX_REVIEW_ITEMS]


def build_job_summary(
    metadata: JobMetadata,
    discrepancies: list[Discrepancy],
    *,
    has_warnings: bool,
) -> JobSummary:
    return JobSummary(
        headline=_outcome_headline(metadata, has_warnings=has_warnings),
        warnings=_user_warnings(metadata),
        review_items=_review_items(discrepancies),
    )


def generate_cover_markdown(
    metadata: JobMetadata,
    discrepancies: list[Discrepancy],
    *,
    has_warnings: bool,
) -> str:
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    summary = build_job_summary(metadata, discrepancies, has_warnings=has_warnings)
    target_label = lang_display_name(metadata.target_lang)
    lines = [
        "# Translation Summary",
        "",
        f"**Document:** {metadata.source_file}",
        f"**Date:** {now}",
        f"**Job reference:** `{metadata.job_id}`",
        "",
        f"**Outcome:** {summary.headline}",
    ]

    if metadata.skipped_translation:
        pass
    elif metadata.source_lang:
        lines.append(
            f"**Language:** {metadata.source_lang} → {target_label} ({metadata.target_lang}) "
            f"(model: {metadata.model})"
        )
    else:
        lines.append(f"**Model:** {metadata.model}")

    if metadata.is_legal_document:
        lines.append("**Document type:** Legal document")

    if (
        not metadata.skipped_translation
        and metadata.translation_mode == TranslationMode.QUICK.value
    ):
        lines.append("**Mode:** Quick (single-pass; no dual-pass verification)")

    if summary.warnings:
        lines.extend(["", "## Warnings", ""])
        for warning in summary.warnings:
            lines.append(f"- {warning}")

    if summary.review_items:
        lines.extend(["", "## Items requiring your attention", ""])
        for item in summary.review_items:
            lines.append(f"- {item}")

    lines.extend(["", "*The translated document begins on the next page.*", ""])
    return "\n".join(lines)
