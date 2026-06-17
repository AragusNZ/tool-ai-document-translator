from __future__ import annotations

from document_translator.errors import IssueCode, IssueSeverity, PipelineIssue
from document_translator.lib.llm import MockLLMClient
from document_translator.models import (
    Discrepancy,
    DiscrepancySeverity,
    ExtractionAlert,
    JobMetadata,
)
from document_translator.report.cover import (
    build_cover_translation_system,
    build_job_summary,
    generate_cover_markdown,
    translate_cover_markdown,
)
from document_translator.types import JobStatus, PipelineStage, TranslationMode


def test_generate_cover_markdown_includes_basics() -> None:
    metadata = JobMetadata(
        job_id="job-1",
        source_file="contract.docx",
        source_lang="es",
        target_lang="fr",
        model="composer-2.5",
    )
    md = generate_cover_markdown(metadata, [], has_warnings=False)
    assert "Translation Summary" in md
    assert "contract.docx" in md
    assert "job-1" in md
    assert "es" in md
    assert "French" in md
    assert "(fr)" in md
    assert "next page" in md


def test_cover_caps_review_items() -> None:
    metadata = JobMetadata(job_id="job-2", source_file="doc.txt")
    discrepancies = [
        Discrepancy(
            chunk_index=i,
            sentence_index=0,
            translation_1="a",
            translation_2="b",
            severity=DiscrepancySeverity.BREAKING,
            explanation=f"issue {i}",
            resolved=False,
        )
        for i in range(8)
    ]
    summary = build_job_summary(metadata, discrepancies, has_warnings=True)
    assert len(summary.review_items) == 5
    assert "more item" in summary.review_items[-1]


def test_cover_caps_warnings() -> None:
    metadata = JobMetadata(
        job_id="job-warn",
        source_file="doc.pdf",
        issues=[
            PipelineIssue(
                code=IssueCode.LOW_TEXT_DENSITY,
                severity=IssueSeverity.WARN,
                message=f"warning {i}",
            )
            for i in range(6)
        ],
    )
    summary = build_job_summary(metadata, [], has_warnings=True)
    assert len(summary.warnings) == 3
    assert summary.warnings[0] == "warning 0"


def test_cover_includes_extraction_alert_warnings() -> None:
    metadata = JobMetadata(
        job_id="job-alert",
        source_file="scan.pdf",
        extraction_alerts=[
            ExtractionAlert(code="LOW_TEXT_DENSITY", severity="warn", message="sparse text"),
        ],
    )
    summary = build_job_summary(metadata, [], has_warnings=True)
    assert "sparse text" in summary.warnings


def test_cover_includes_quick_mode_note() -> None:
    metadata = JobMetadata(
        job_id="job-quick",
        source_file="doc.txt",
        source_lang="es",
        target_lang="en",
        translation_mode=TranslationMode.QUICK.value,
    )
    md = generate_cover_markdown(metadata, [], has_warnings=False)
    assert "Quick (single-pass" in md


def test_cover_omits_quick_mode_note_when_skipped() -> None:
    metadata = JobMetadata(
        job_id="job-skip",
        source_file="doc.txt",
        skipped_translation=True,
        translation_mode=TranslationMode.QUICK.value,
    )
    md = generate_cover_markdown(metadata, [], has_warnings=False)
    assert "Quick (single-pass" not in md


def test_cover_includes_warnings() -> None:
    metadata = JobMetadata(
        job_id="job-3",
        source_file="doc.pdf",
        issues=[
            PipelineIssue(
                code=IssueCode.EXPORT_FAILED,
                severity=IssueSeverity.WARN,
                message="export failed",
                stage=PipelineStage.EXPORTING,
            )
        ],
    )
    md = generate_cover_markdown(metadata, [], has_warnings=True)
    assert "Warnings" in md
    assert "export failed" in md


def test_summary_failed_outcome() -> None:
    metadata = JobMetadata(
        job_id="job-4",
        source_file="doc.pdf",
        job_status=JobStatus.FAILED,
    )
    summary = build_job_summary(metadata, [], has_warnings=False)
    assert "did not complete" in summary.headline


def test_summary_skipped_translation_uses_target_language() -> None:
    metadata = JobMetadata(
        job_id="job-5",
        source_file="doc.txt",
        skipped_translation=True,
        target_lang="es",
    )
    summary = build_job_summary(metadata, [], has_warnings=False)
    assert "Spanish" in summary.headline


def test_build_cover_translation_system_includes_target_language() -> None:
    system = build_cover_translation_system("fr")
    assert "French" in system
    assert "(fr)" in system


def test_translate_cover_markdown_skips_english() -> None:
    mock = MockLLMClient()
    cover = "# Translation Summary\n\n**Outcome:** Done."
    assert translate_cover_markdown(mock, cover, target_lang="en") == cover
    assert mock.tracker.count == 0


def test_translate_cover_markdown_calls_llm_for_non_english() -> None:
    mock = MockLLMClient(prefix="[FR] ")
    cover = "# Translation Summary\n\n**Outcome:** Done."
    result = translate_cover_markdown(mock, cover, target_lang="fr")
    assert mock.tracker.count == 1
    assert result.startswith("[FR] ")
    _system, user = mock.calls[0]
    assert "French" in _system
    assert cover in user
