from __future__ import annotations

from document_translator.errors import IssueCode, IssueSeverity
from document_translator.models import (
    Discrepancy,
    DiscrepancySeverity,
    ExtractionAlert,
    JobMetadata,
)
from document_translator.report.results import generate_results_markdown
from document_translator.types import JobStatus


def test_generate_results_markdown_with_extraction_alerts() -> None:
    metadata = JobMetadata(
        job_id="alert-job",
        source_file="scan.pdf",
        extraction_alerts=[
            ExtractionAlert(code="LOW_TEXT_DENSITY", severity="warn", message="possible scanned PDF"),
        ],
    )
    md = generate_results_markdown(metadata, [])
    assert "LOW_TEXT_DENSITY" in md
    assert "possible scanned PDF" in md


def test_generate_results_markdown_with_discrepancies_table() -> None:
    metadata = JobMetadata(
        job_id="disc-job",
        source_file="doc.txt",
        source_lang="es",
        target_lang="fr",
    )
    discrepancies = [
        Discrepancy(
            chunk_index=0,
            sentence_index=1,
            translation_1="A",
            translation_2="B",
            severity=DiscrepancySeverity.HIGH,
            explanation="modal verb differs",
            resolved=True,
        )
    ]
    md = generate_results_markdown(metadata, discrepancies)
    assert "## Discrepancies" in md
    assert "modal verb differs" in md
    assert "| 0 | 1 |" in md
    assert "French" in md
    assert "`fr`" in md


def test_generate_results_markdown_skipped_translation_uses_target_lang() -> None:
    metadata = JobMetadata(
        job_id="skip-job",
        source_file="doc.txt",
        skipped_translation=True,
        source_lang="es",
        target_lang="es",
    )
    md = generate_results_markdown(metadata, [])
    assert "already in Spanish" in md


def test_generate_results_markdown_no_translate() -> None:
    metadata = JobMetadata(
        job_id="no-translate-job",
        source_file="doc.txt",
        no_translate=True,
        skipped_translation=True,
        source_lang="es",
        target_lang="en",
    )
    md = generate_results_markdown(metadata, [])
    assert "--no-translate" in md
    assert "original text was exported" in md


def test_generate_results_markdown_with_issues_and_availability() -> None:
    from document_translator.errors import PipelineIssue
    from document_translator.types import PipelineStage

    metadata = JobMetadata(
        job_id="issues-job",
        source_file="doc.txt",
        issues=[
            PipelineIssue(
                code=IssueCode.EXPORT_FAILED,
                severity=IssueSeverity.WARN,
                message="export failed",
                stage=PipelineStage.EXPORTING,
            )
        ],
        artifact_availability={"final_output": False, "metadata_json": True},
        duration_seconds=12.5,
        job_status=JobStatus.COMPLETED_WITH_WARNINGS,
    )
    md = generate_results_markdown(metadata, [])
    assert "EXPORT_FAILED" in md
    assert "final_output: no" in md
    assert "12.5s" in md
