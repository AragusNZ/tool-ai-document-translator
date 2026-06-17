from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from document_translator.config.languages import lang_display_name
from document_translator.models import Discrepancy, DiscrepancySeverity, JobMetadata
from document_translator.types import JobStatus


def generate_results_markdown(
    metadata: JobMetadata,
    discrepancies: list[Discrepancy],
) -> str:
    now = datetime.now(UTC).isoformat()
    status = metadata.job_status.value if metadata.job_status else "unknown"
    lines = [
        "# Translation Results Report",
        "",
        f"Generated: {now}",
        f"Job ID: `{metadata.job_id}`",
        f"Source file: `{metadata.source_file}`",
        "",
        "## Job Outcome",
        "",
        f"- Status: `{status}`",
    ]

    if metadata.failed_stage:
        lines.append(f"- Failed at stage: `{metadata.failed_stage.value}`")
    if metadata.error_code:
        lines.append(f"- Error code: `{metadata.error_code.value}`")
    if metadata.error_message:
        lines.extend(["", "## Failure", "", metadata.error_message])

    lines.extend(["", "## Summary", ""])

    if metadata.skipped_translation:
        target = lang_display_name(metadata.target_lang)
        lines.append(
            f"Source document was already in {target}. Translation was skipped; text was copied through."
        )
    elif status != JobStatus.FAILED.value:
        target = lang_display_name(metadata.target_lang)
        lines.append(
            f"Translated from **{metadata.source_lang or 'unknown'}** to {target} "
            f"(`{metadata.target_lang}`) using model `{metadata.model}`."
        )
    else:
        lines.append("Translation did not complete successfully.")

    lines.extend(
        [
            "",
            "## Language Detection",
            "",
            f"- Detected language: `{metadata.source_lang or 'unknown'}`",
            f"- Target language: `{metadata.target_lang}` ({lang_display_name(metadata.target_lang)})",
            f"- Confidence: {metadata.source_lang_confidence if metadata.source_lang_confidence is not None else 'n/a'}",
            f"- AI fallback used: {'yes' if metadata.lang_used_ai else 'no'}",
            "",
            "## Document Classification",
            "",
            f"- Legal document heuristic: **{'yes' if metadata.is_legal_document else 'no'}**",
            f"- Legal classification AI used: {'yes' if metadata.legal_used_ai else 'no'}",
            f"- Conversion method: `{metadata.conversion_method or 'n/a'}`",
            f"- Page count: {metadata.page_count if metadata.page_count is not None else 'n/a'}",
            f"- Chunks processed: {metadata.chunk_count}",
            f"- LLM calls: {metadata.llm_call_count}",
            f"- Export format: `{metadata.export_format or 'n/a'}`",
            f"- Final document exported: {'yes' if metadata.final_exported else 'no'}",
            "",
            "## Extraction Alerts",
            "",
        ]
    )

    if metadata.extraction_alerts:
        for alert in metadata.extraction_alerts:
            lines.append(f"- **{alert.code}** ({alert.severity}): {alert.message}")
    else:
        lines.append("_(none)_")

    lines.extend(["", "## Warnings and Errors", ""])
    if metadata.issues:
        lines.append("| Code | Severity | Stage | Message |")
        lines.append("|------|----------|-------|---------|")
        for issue in metadata.issues:
            stage = issue.stage.value if issue.stage else ""
            msg = (issue.message or "").replace("|", "/")
            lines.append(f"| {issue.code.value} | {issue.severity.value} | {stage} | {msg} |")
    else:
        lines.append("_(none)_")

    lines.extend(["", "## Artifact Availability", ""])
    if metadata.artifact_availability:
        for name, available in sorted(metadata.artifact_availability.items()):
            lines.append(f"- {name}: {'yes' if available else 'no'}")
    else:
        lines.append("_(none)_")

    lines.extend(["", "## Discrepancies", ""])
    if not discrepancies:
        lines.append("No discrepancies detected between translation passes.")
    else:
        lines.append("| Chunk | Sentence | Severity | Resolved | Explanation |")
        lines.append("|-------|----------|----------|----------|-------------|")
        for d in discrepancies:
            expl = (d.explanation or "").replace("|", "/")
            lines.append(
                f"| {d.chunk_index} | {d.sentence_index} | {d.severity.value} | "
                f"{'yes' if d.resolved else 'no'} | {expl} |"
            )

    breaking_unresolved = [
        d for d in discrepancies if d.severity == DiscrepancySeverity.BREAKING and not d.resolved
    ]
    lines.extend(["", "## Issues Requiring Human Review", ""])
    if breaking_unresolved:
        for d in breaking_unresolved:
            lines.append(f"- **Breaking** (chunk {d.chunk_index}, sentence {d.sentence_index}): {d.explanation}")
    else:
        lines.append("_(none)_")

    if metadata.duration_seconds is not None:
        lines.extend(["", "## Timing", "", f"- Total duration: {metadata.duration_seconds:.1f}s"])

    return "\n".join(lines) + "\n"


def write_results(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
