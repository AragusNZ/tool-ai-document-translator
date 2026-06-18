from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from document_translator.config.formats import ExportFormat
from document_translator.config.settings import PipelineConfig
from document_translator.errors import IssueCode, IssueSeverity
from document_translator.lib.llm import MockLLMClient
from document_translator.models import (
    ArtifactPaths,
    Discrepancy,
    DiscrepancySeverity,
    JobMetadata,
    JobResult,
    TranslationOptions,
)
from document_translator.pipeline import DocumentTranslationService
from document_translator.report.collector import IssueCollector
from document_translator.report.results import generate_results_markdown
from document_translator.storage.paths import JobPaths
from document_translator.types import JobStatus, PipelineStage, TranslationMode


def test_legal_detection() -> None:
    from document_translator.detect.legal import is_legal_document

    assert is_legal_document("WHEREAS the parties shall indemnify liability under this agreement.")


@pytest.mark.integration
def test_pipeline_e2e_mock(spanish_contract: Path, tmp_path: Path) -> None:
    mock = MockLLMClient(prefix="[EN] ")
    translation_pass = 0

    def divergent_on_second_pass(system: str, user: str) -> str:
        nonlocal translation_pass
        mock.calls.append((system, user))
        if "equivalent" in system.lower():
            return '{"equivalent": false, "severity": "high", "explanation": "modal verb differs"}'
        if "adjudicate" in system.lower() or "choose" in system.lower() or "variant" in user.lower():
            return json.dumps(
                {"chosen": 3, "resolved_text": "[EN] resolved shall pay", "rationale": "legal precision"}
            )
        if "language" in system.lower():
            return "es"
        if "professional document translator" in system.lower() and "Chunk" in user:
            translation_pass += 1
            if translation_pass >= 2:
                return "The Buyer may cancel this agreement without notice."
            return "The Seller shall deliver all goods within thirty days."
        return "[EN] " + user.split("\n\n")[-1][:120]

    mock.complete = divergent_on_second_pass  # type: ignore[method-assign]

    config = PipelineConfig(runs_dir=tmp_path / "runs", root=tmp_path)
    service = DocumentTranslationService(config=config, llm=mock)

    def _touch_export(source: Path, target: Path, fmt: ExportFormat, **kwargs: object) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("exported", encoding="utf-8")
        assert "Translation Summary" in source.read_text(encoding="utf-8")

    with patch("document_translator.pipeline.export_markdown", side_effect=_touch_export):
        result = service.translate(
            spanish_contract,
            TranslationOptions(job_id="test-job-1", translation_mode=TranslationMode.THOROUGH),
        )

    assert result.status.value == "completed"
    assert result.metadata.source_lang == "es"
    assert result.artifacts.status_json is not None
    status = json.loads(result.artifacts.status_json.read_text())
    assert status["terminal_status"] == "completed"
    assert result.metadata.export_format == "txt"
    assert result.artifacts.final_output is not None
    assert result.artifacts.final_output.name == "05-final.txt"
    assert result.metadata.summary is not None
    job_root = tmp_path / "runs" / "test-job-1"
    assert not (job_root / "artifacts" / "01-extracted.md").exists()
    assert not (job_root / "artifacts" / "04-resolved.md").exists()
    assert not (job_root / "artifacts" / "results.md").exists()
    assert not (job_root / "discrepancies.json").exists()
    assert not (job_root / "input").exists()
    assert result.metadata.artifact_availability == {
        "final_output": True,
        "resolved_md": False,
        "metadata_json": True,
        "status_json": True,
        "extraction_layout_json": False,
        "screenshots_dir": False,
        "checkpoint_json": False,
        "checkpoints_dir": False,
    }
    metadata_payload = json.loads(result.artifacts.metadata_json.read_text())  # type: ignore[union-attr]
    assert "discrepancies" in metadata_payload
    assert "summary" in metadata_payload
    assert "issues" in result.model_dump_json_api()
    assert len(result.discrepancies) > 0
    assert any(d.resolved for d in result.discrepancies)
    assert result.metadata.discrepancy_count == len(result.discrepancies)
    assert result.metadata.unresolved_breaking_count == 0


@pytest.mark.integration
def test_export_failure_completed_with_warnings(spanish_contract: Path, tmp_path: Path) -> None:
    mock = MockLLMClient(prefix="[EN] ")
    config = PipelineConfig(runs_dir=tmp_path / "runs", root=tmp_path)
    service = DocumentTranslationService(config=config, llm=mock)

    with patch("document_translator.pipeline.export_markdown", side_effect=RuntimeError("pandoc failed")):
        result = service.translate(
            spanish_contract,
            TranslationOptions(job_id="export-fail-job", export_format=ExportFormat.PDF),
        )

    assert result.status == JobStatus.COMPLETED_WITH_WARNINGS
    assert result.metadata.final_exported is False
    assert result.metadata.export_format == "pdf"
    assert any(i.code == IssueCode.EXPORT_FAILED for i in result.metadata.issues)


@pytest.mark.integration
def test_hard_failure_writes_metadata_json(tmp_path: Path) -> None:
    path = tmp_path / "doc.txt"
    path.write_text(
        "POR CUANTO las partes convienen en celebrar el presente contrato legal.\n" * 8,
        encoding="utf-8",
    )
    mock = MockLLMClient()

    def fail_translate(system: str, user: str) -> str:
        if "Chunk" in user:
            raise RuntimeError("LLM down")
        return "es"

    mock.complete = fail_translate  # type: ignore[method-assign]
    config = PipelineConfig(runs_dir=tmp_path / "runs", root=tmp_path)
    service = DocumentTranslationService(config=config, llm=mock)
    with patch("document_translator.pipeline.export_markdown"):
        result = service.translate(path, TranslationOptions(job_id="hard-fail-job"))

    assert result.status == JobStatus.FAILED
    assert result.artifacts.metadata_json is not None
    assert result.artifacts.metadata_json.exists()
    assert result.metadata.failed_stage is not None
    status = json.loads(result.artifacts.status_json.read_text())  # type: ignore[union-attr]
    assert status["progress"] > 0


@pytest.mark.integration
def test_unsupported_format_creates_job_dir(tmp_path: Path) -> None:
    bad = tmp_path / "file.xyz"
    bad.write_text("data", encoding="utf-8")
    config = PipelineConfig(runs_dir=tmp_path / "runs", root=tmp_path)
    service = DocumentTranslationService(config=config, llm=MockLLMClient())
    result = service.translate(bad, TranslationOptions(job_id="bad-ext-job"))

    assert result.status == JobStatus.FAILED
    assert (tmp_path / "runs" / "bad-ext-job" / "status.json").exists()
    assert result.error_code == IssueCode.UNSUPPORTED_FORMAT


def test_issue_collector_in_metadata_and_api_json() -> None:
    collector = IssueCollector()
    collector.add(IssueCode.EXPORT_FAILED, IssueSeverity.WARN, "test")
    metadata = JobMetadata(
        job_id="j1",
        source_file="a.txt",
        issues=collector.to_list(),
        job_status=JobStatus.COMPLETED_WITH_WARNINGS,
    )
    md = generate_results_markdown(metadata, [])
    assert "EXPORT_FAILED" in md

    result = JobResult(
        job_id="j1",
        status=JobStatus.COMPLETED_WITH_WARNINGS,
        artifacts=ArtifactPaths(),
        metadata=metadata,
    )
    api = result.model_dump_json_api()
    assert api["status"] == "completed_with_warnings"
    assert len(api["issues"]) == 1
    assert api["issues"][0]["code"] == "EXPORT_FAILED"


def test_generate_results_markdown_failure_section() -> None:
    metadata = JobMetadata(
        job_id="fail-job",
        source_file="doc.txt",
        job_status=JobStatus.FAILED,
        failed_stage=PipelineStage.TRANSLATING,
        error_code=IssueCode.PIPELINE_FAILED,
        error_message="LLM down",
    )
    md = generate_results_markdown(metadata, [])
    assert "## Failure" in md
    assert "LLM down" in md
    assert "TRANSLATING" in md or "translating" in md.lower()


def test_generate_results_markdown_skipped_translation() -> None:
    metadata = JobMetadata(
        job_id="skip-job",
        source_file="doc.txt",
        skipped_translation=True,
        source_lang="en",
        target_lang="en",
    )
    md = generate_results_markdown(metadata, [])
    assert "already in English" in md


@pytest.mark.integration
def test_english_source_translates_when_target_not_english(english_doc: Path, tmp_path: Path) -> None:
    mock = MockLLMClient(prefix="[FR] ")
    config = PipelineConfig(runs_dir=tmp_path / "runs", root=tmp_path)
    service = DocumentTranslationService(config=config, llm=mock)

    def _touch_export(source: Path, target: Path, fmt: ExportFormat, **kwargs: object) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("exported", encoding="utf-8")

    with patch("document_translator.pipeline.export_markdown", side_effect=_touch_export):
        result = service.translate(
            english_doc,
            TranslationOptions(job_id="english-to-french-job", target_lang="fr"),
        )

    assert result.status == JobStatus.COMPLETED
    assert result.metadata.skipped_translation is False
    assert result.metadata.target_lang == "fr"
    assert mock.tracker.count > 0


@pytest.mark.integration
def test_cover_translated_in_final_export_for_non_english_target(
    english_doc: Path, tmp_path: Path
) -> None:
    mock = MockLLMClient(prefix="[FR] ")
    config = PipelineConfig(runs_dir=tmp_path / "runs", root=tmp_path, keep_work_files=True)
    service = DocumentTranslationService(config=config, llm=mock)

    def _touch_export(source: Path, target: Path, fmt: ExportFormat, **kwargs: object) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("exported", encoding="utf-8")

    with patch("document_translator.pipeline.export_markdown", side_effect=_touch_export):
        result = service.translate(
            english_doc,
            TranslationOptions(job_id="french-cover-job", target_lang="fr"),
        )

    combined = tmp_path / "runs" / "french-cover-job" / "artifacts" / ".combined-export.md"
    assert result.status == JobStatus.COMPLETED
    assert combined.exists()
    assert "[FR]" in combined.read_text(encoding="utf-8")


@pytest.mark.integration
def test_cover_translation_failure_falls_back_to_english(english_doc: Path, tmp_path: Path) -> None:
    mock = MockLLMClient(prefix="[FR] ")
    config = PipelineConfig(runs_dir=tmp_path / "runs", root=tmp_path, keep_work_files=True)
    service = DocumentTranslationService(config=config, llm=mock)

    def _touch_export(source: Path, target: Path, fmt: ExportFormat, **kwargs: object) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("exported", encoding="utf-8")

    with (
        patch("document_translator.pipeline.translate_cover_markdown", side_effect=RuntimeError("cover LLM down")),
        patch("document_translator.pipeline.export_markdown", side_effect=_touch_export),
    ):
        result = service.translate(
            english_doc,
            TranslationOptions(job_id="cover-fallback-job", target_lang="fr"),
        )

    combined = tmp_path / "runs" / "cover-fallback-job" / "artifacts" / ".combined-export.md"
    combined_text = combined.read_text(encoding="utf-8")
    cover_section = combined_text.split("\n---\n", maxsplit=1)[0]
    assert result.status == JobStatus.COMPLETED_WITH_WARNINGS
    assert "Translation Summary" in cover_section
    assert "[FR]" not in cover_section
    assert any(i.code == IssueCode.COVER_TRANSLATION_FAILED for i in result.metadata.issues)


@pytest.mark.integration
def test_no_translate_skips_translation_and_exports(spanish_contract: Path, tmp_path: Path) -> None:
    mock = MockLLMClient(prefix="[EN] ")
    config = PipelineConfig(runs_dir=tmp_path / "runs", root=tmp_path, keep_work_files=True)
    service = DocumentTranslationService(config=config, llm=mock)

    def _touch_export(source: Path, target: Path, fmt: ExportFormat, **kwargs: object) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("exported", encoding="utf-8")

    def _translation_calls() -> int:
        return sum(
            1
            for system, _ in mock.calls
            if "professional document translator" in system.lower()
        )

    with patch("document_translator.pipeline.export_markdown", side_effect=_touch_export):
        result = service.translate(
            spanish_contract,
            TranslationOptions(job_id="no-translate-job", no_translate=True, target_lang="en"),
        )

    assert result.status == JobStatus.COMPLETED
    assert result.metadata.skipped_translation is True
    assert result.metadata.no_translate is True
    assert result.metadata.source_lang == "es"
    assert result.discrepancies == []
    assert result.artifacts.final_output is not None
    assert _translation_calls() == 0

    job_root = tmp_path / "runs" / "no-translate-job"
    resolved = (job_root / "artifacts" / "04-resolved.md").read_text(encoding="utf-8")
    assert "CONTRATO" in resolved or "contrato" in resolved.lower()


@pytest.mark.integration
def test_save_resolved_keeps_resolved_artifact(spanish_contract: Path, tmp_path: Path) -> None:
    mock = MockLLMClient(prefix="[EN] ")
    config = PipelineConfig(runs_dir=tmp_path / "runs", root=tmp_path)
    service = DocumentTranslationService(config=config, llm=mock)

    def _touch_export(source: Path, target: Path, fmt: ExportFormat, **kwargs: object) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("exported", encoding="utf-8")

    with patch("document_translator.pipeline.export_markdown", side_effect=_touch_export):
        result = service.translate(
            spanish_contract,
            TranslationOptions(job_id="save-resolved-job", save_resolved=True),
        )

    assert result.status == JobStatus.COMPLETED
    assert result.metadata.save_resolved is True
    assert result.metadata.artifact_availability["resolved_md"] is True
    assert result.artifacts.resolved_md is not None

    job_root = tmp_path / "runs" / "save-resolved-job"
    assert (job_root / "artifacts" / "04-resolved.md").exists()
    assert not (job_root / "artifacts" / "01-extracted.md").exists()


@pytest.mark.integration
def test_no_cover_page_exports_body_only(spanish_contract: Path, tmp_path: Path) -> None:
    mock = MockLLMClient(prefix="[EN] ")
    config = PipelineConfig(runs_dir=tmp_path / "runs", root=tmp_path, keep_work_files=True)
    service = DocumentTranslationService(config=config, llm=mock)

    captured_combined: list[str] = []

    def _capture_export(source: Path, target: Path, fmt: ExportFormat, **kwargs: object) -> None:
        captured_combined.append(source.read_text(encoding="utf-8"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("exported", encoding="utf-8")

    with patch("document_translator.pipeline.export_markdown", side_effect=_capture_export):
        result = service.translate(
            spanish_contract,
            TranslationOptions(job_id="no-cover-job", no_cover_page=True),
        )

    assert result.status == JobStatus.COMPLETED
    assert result.metadata.no_cover_page is True
    assert len(captured_combined) == 1
    combined = captured_combined[0]
    assert "# Translation Summary" not in combined
    assert '<div class="cover-page">' not in combined
    assert "\\newpage" not in combined


@pytest.mark.integration
def test_save_resolved_and_no_cover_page_combined(spanish_contract: Path, tmp_path: Path) -> None:
    mock = MockLLMClient(prefix="[EN] ")
    config = PipelineConfig(runs_dir=tmp_path / "runs", root=tmp_path, keep_work_files=True)
    service = DocumentTranslationService(config=config, llm=mock)

    captured_combined: list[str] = []

    def _capture_export(source: Path, target: Path, fmt: ExportFormat, **kwargs: object) -> None:
        captured_combined.append(source.read_text(encoding="utf-8"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("exported", encoding="utf-8")

    with patch("document_translator.pipeline.export_markdown", side_effect=_capture_export):
        result = service.translate(
            spanish_contract,
            TranslationOptions(
                job_id="both-flags-job",
                save_resolved=True,
                no_cover_page=True,
            ),
        )

    assert result.status == JobStatus.COMPLETED
    assert result.metadata.save_resolved is True
    assert result.metadata.no_cover_page is True
    assert result.artifacts.resolved_md is not None
    assert (tmp_path / "runs" / "both-flags-job" / "artifacts" / "04-resolved.md").exists()
    assert "# Translation Summary" not in captured_combined[0]


@pytest.mark.integration
def test_spanish_source_skips_when_target_matches(spanish_contract: Path, tmp_path: Path) -> None:
    mock = MockLLMClient(prefix="[ES] ")
    config = PipelineConfig(runs_dir=tmp_path / "runs", root=tmp_path)
    service = DocumentTranslationService(config=config, llm=mock)

    def _touch_export(source: Path, target: Path, fmt: ExportFormat, **kwargs: object) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("exported", encoding="utf-8")

    with patch("document_translator.pipeline.export_markdown", side_effect=_touch_export):
        result = service.translate(
            spanish_contract,
            TranslationOptions(job_id="spanish-skip-job", target_lang="es"),
        )

    assert result.status == JobStatus.COMPLETED
    assert result.metadata.skipped_translation is True
    assert result.metadata.no_translate is False
    assert result.metadata.source_lang == "es"
    assert result.metadata.target_lang == "es"
    assert result.discrepancies == []


@pytest.mark.integration
def test_fail_on_empty_extraction(tmp_path: Path) -> None:
    empty = tmp_path / "empty.txt"
    empty.write_text("   \n", encoding="utf-8")
    config = PipelineConfig(runs_dir=tmp_path / "runs", root=tmp_path, fail_on_empty_extraction=True)
    service = DocumentTranslationService(config=config, llm=MockLLMClient())
    result = service.translate(empty, TranslationOptions(job_id="empty-fail-job"))
    assert result.status == JobStatus.FAILED
    assert result.error_code == IssueCode.EMPTY_EXTRACTION


@pytest.mark.integration
def test_failure_writes_metadata_and_cleans_working_files(spanish_contract: Path, tmp_path: Path) -> None:
    mock = MockLLMClient(prefix="[EN] ")
    config = PipelineConfig(runs_dir=tmp_path / "runs", root=tmp_path)
    service = DocumentTranslationService(config=config, llm=mock)

    with patch("document_translator.pipeline.reconcile_translations", side_effect=RuntimeError("reconcile blew up")):
        result = service.translate(
            spanish_contract,
            TranslationOptions(
                job_id="preserve-disc-job",
                force_overwrite=True,
                translation_mode=TranslationMode.THOROUGH,
            ),
        )

    assert result.status == JobStatus.FAILED
    assert result.artifacts.metadata_json is not None
    job_root = tmp_path / "runs" / "preserve-disc-job"
    assert not (job_root / "artifacts" / "04-resolved.md").exists()


def test_write_status_atomic(tmp_path: Path) -> None:
    paths = JobPaths(tmp_path / "runs", "status-job", export_format=ExportFormat.PDF)
    paths.ensure_dirs()
    paths.write_status(PipelineStage.EXTRACTING, message="working", progress=0.5, issue_count=0)
    assert paths.status_json.exists()
    payload = json.loads(paths.status_json.read_text())
    assert payload["status"] == "in_progress"


@pytest.mark.integration
def test_english_source_skips_translation(english_doc: Path, tmp_path: Path) -> None:
    mock = MockLLMClient(prefix="[EN] ")
    config = PipelineConfig(runs_dir=tmp_path / "runs", root=tmp_path)
    service = DocumentTranslationService(config=config, llm=mock)

    def _touch_export(source: Path, target: Path, fmt: ExportFormat, **kwargs: object) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("exported", encoding="utf-8")

    with patch("document_translator.pipeline.export_markdown", side_effect=_touch_export):
        result = service.translate(english_doc, TranslationOptions(job_id="english-skip-job"))

    assert result.status == JobStatus.COMPLETED
    assert result.metadata.skipped_translation is True
    assert result.metadata.source_lang == "en"
    assert result.discrepancies == []
    assert result.artifacts.final_output is not None


@pytest.mark.integration
def test_identical_passes_no_discrepancies(spanish_contract: Path, tmp_path: Path) -> None:
    mock = MockLLMClient(prefix="[EN] ")
    config = PipelineConfig(runs_dir=tmp_path / "runs", root=tmp_path)
    service = DocumentTranslationService(config=config, llm=mock)

    def _touch_export(source: Path, target: Path, fmt: ExportFormat, **kwargs: object) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("exported", encoding="utf-8")

    with patch("document_translator.pipeline.export_markdown", side_effect=_touch_export):
        result = service.translate(
            spanish_contract,
            TranslationOptions(job_id="identical-passes-job", translation_mode=TranslationMode.THOROUGH),
        )

    assert result.status == JobStatus.COMPLETED
    assert result.discrepancies == []
    assert result.metadata.discrepancies == []


@pytest.mark.integration
def test_quick_mode_single_pass(spanish_contract: Path, tmp_path: Path) -> None:
    mock = MockLLMClient(prefix="[EN] ")
    config = PipelineConfig(runs_dir=tmp_path / "runs", root=tmp_path)
    service = DocumentTranslationService(config=config, llm=mock)

    def _touch_export(source: Path, target: Path, fmt: ExportFormat, **kwargs: object) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("exported", encoding="utf-8")

    def _translation_calls() -> int:
        return sum(
            1
            for system, _ in mock.calls
            if "professional document translator" in system.lower()
        )

    with patch("document_translator.pipeline.export_markdown", side_effect=_touch_export):
        quick_result = service.translate(
            spanish_contract,
            TranslationOptions(job_id="quick-mode-job", translation_mode=TranslationMode.QUICK),
        )
        quick_calls = _translation_calls()
        mock.calls.clear()
        mock.tracker.count = 0
        service.translate(
            spanish_contract,
            TranslationOptions(
                job_id="thorough-mode-job",
                translation_mode=TranslationMode.THOROUGH,
                force_overwrite=True,
            ),
        )
        thorough_calls = _translation_calls()

    assert quick_result.status == JobStatus.COMPLETED
    assert quick_result.metadata.translation_mode == TranslationMode.QUICK.value
    assert quick_result.metadata.discrepancy_count == 0
    assert quick_result.discrepancies == []
    assert quick_result.metadata.llm_call_count > 0
    assert quick_result.metadata.llm_usage.input_tokens > 0
    assert quick_result.metadata.llm_usage.output_tokens > 0
    assert quick_result.metadata.llm_usage.estimated_cost_usd is not None
    assert quick_calls > 0
    assert thorough_calls > quick_calls
    assert quick_result.artifacts.status_json is not None
    quick_status = json.loads(quick_result.artifacts.status_json.read_text())
    assert quick_status["terminal_status"] == "completed"
    assert quick_status["message"] != "Comparing and resolving discrepancies"


@pytest.mark.integration
def test_thorough_unresolved_breaking_count(spanish_contract: Path, tmp_path: Path) -> None:
    mock = MockLLMClient(prefix="[EN] ")
    config = PipelineConfig(runs_dir=tmp_path / "runs", root=tmp_path)
    service = DocumentTranslationService(config=config, llm=mock)

    breaking_unresolved = Discrepancy(
        chunk_index=0,
        sentence_index=0,
        translation_1="The party shall pay.",
        translation_2="The party may pay.",
        severity=DiscrepancySeverity.BREAKING,
        resolved=False,
        explanation="unresolved breaking test",
    )

    def _touch_export(source: Path, target: Path, fmt: ExportFormat, **kwargs: object) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("exported", encoding="utf-8")

    with (
        patch(
            "document_translator.pipeline.reconcile_translations",
            return_value=("[EN] resolved text", [breaking_unresolved]),
        ),
        patch("document_translator.pipeline.export_markdown", side_effect=_touch_export),
    ):
        result = service.translate(
            spanish_contract,
            TranslationOptions(job_id="breaking-unresolved-job", translation_mode=TranslationMode.THOROUGH),
        )

    assert result.status == JobStatus.COMPLETED
    assert result.metadata.unresolved_breaking_count == 1
    assert result.metadata.discrepancy_count == 1


@pytest.mark.integration
def test_thorough_same_lang_skip(english_doc: Path, tmp_path: Path) -> None:
    mock = MockLLMClient(prefix="[EN] ")
    config = PipelineConfig(runs_dir=tmp_path / "runs", root=tmp_path)
    service = DocumentTranslationService(config=config, llm=mock)
    captured_stages: list[str] = []
    original_write_status = JobPaths.write_status

    def capture_write_status(self, stage, **kwargs):  # noqa: ANN001, ANN003
        captured_stages.append(stage.value)
        return original_write_status(self, stage, **kwargs)

    def _touch_export(source: Path, target: Path, fmt: ExportFormat, **kwargs: object) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("exported", encoding="utf-8")

    with (
        patch.object(JobPaths, "write_status", capture_write_status),
        patch("document_translator.pipeline.export_markdown", side_effect=_touch_export),
    ):
        result = service.translate(
            english_doc,
            TranslationOptions(job_id="thorough-skip-job", translation_mode=TranslationMode.THOROUGH),
        )

    translation_calls = sum(
        1 for system, _ in mock.calls if "professional document translator" in system.lower()
    )
    assert result.status == JobStatus.COMPLETED
    assert result.metadata.skipped_translation is True
    assert result.metadata.translation_mode == TranslationMode.THOROUGH.value
    assert result.discrepancies == []
    assert result.metadata.discrepancy_count == 0
    assert "reconciling" not in captured_stages
    assert "translating" not in captured_stages
    assert translation_calls == 0


@pytest.mark.integration
def test_status_stage_progression(spanish_contract: Path, tmp_path: Path) -> None:
    mock = MockLLMClient(prefix="[EN] ")
    config = PipelineConfig(runs_dir=tmp_path / "runs", root=tmp_path)
    service = DocumentTranslationService(config=config, llm=mock)
    captured_stages: list[str] = []
    original_write_status = JobPaths.write_status

    def capture_write_status(self, stage, **kwargs):  # noqa: ANN001, ANN003
        captured_stages.append(stage.value)
        return original_write_status(self, stage, **kwargs)

    def _touch_export(source: Path, target: Path, fmt: ExportFormat, **kwargs: object) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("exported", encoding="utf-8")

    with (
        patch.object(JobPaths, "write_status", capture_write_status),
        patch("document_translator.pipeline.export_markdown", side_effect=_touch_export),
    ):
        result = service.translate(
            spanish_contract,
            TranslationOptions(job_id="stage-progress-job", translation_mode=TranslationMode.THOROUGH),
        )

    assert result.status == JobStatus.COMPLETED
    assert captured_stages[0] == "queued"
    assert "extracting" in captured_stages
    assert "detecting_language" in captured_stages
    assert "translating" in captured_stages
    assert "reconciling" in captured_stages
    assert "exporting" in captured_stages
    assert captured_stages[-1] == "completed"
    assert captured_stages.index("extracting") < captured_stages.index("detecting_language")
    assert captured_stages.index("detecting_language") < captured_stages.index("translating")
    assert captured_stages.index("translating") < captured_stages.index("reconciling")
    assert captured_stages.index("reconciling") < captured_stages.index("exporting")


@pytest.mark.integration
@pytest.mark.requires_pandoc
def test_pipeline_quick_export_txt_real(spanish_contract: Path, tmp_path: Path) -> None:
    import shutil

    if shutil.which("pandoc") is None:
        pytest.skip("pandoc not available")

    mock = MockLLMClient(prefix="[EN] ")
    config = PipelineConfig(runs_dir=tmp_path / "runs", root=tmp_path)
    service = DocumentTranslationService(config=config, llm=mock)

    result = service.translate(
        spanish_contract,
        TranslationOptions(job_id="real-export-job", export_format=ExportFormat.TXT),
    )

    assert result.status == JobStatus.COMPLETED
    assert result.artifacts.final_output is not None
    assert result.artifacts.final_output.stat().st_size > 0
    assert result.metadata.final_exported is True


@pytest.mark.integration
def test_chunk_count_mismatch_at_pipeline(spanish_contract: Path, tmp_path: Path) -> None:
    mock = MockLLMClient(prefix="[EN] ")
    config = PipelineConfig(runs_dir=tmp_path / "runs", root=tmp_path)
    service = DocumentTranslationService(config=config, llm=mock)
    call_count = 0

    def uneven_translate(*args, **kwargs):  # noqa: ANN002, ANN003
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return ["chunk one"]
        return ["chunk one", "chunk two"]

    with (
        patch("document_translator.pipeline.translate_source_chunks", side_effect=uneven_translate),
        patch("document_translator.pipeline.export_markdown"),
    ):
        result = service.translate(
            spanish_contract,
            TranslationOptions(job_id="chunk-mismatch-job", translation_mode=TranslationMode.THOROUGH),
        )

    assert result.status == JobStatus.FAILED
    assert result.error_code == IssueCode.CHUNK_COUNT_MISMATCH


def test_translate_batch_processes_all_items_despite_failure(tmp_path: Path) -> None:
    doc_a = tmp_path / "a.txt"
    doc_b = tmp_path / "b.txt"
    doc_a.write_text("hello", encoding="utf-8")
    doc_b.write_text("world", encoding="utf-8")
    config = PipelineConfig(runs_dir=tmp_path / "runs", root=tmp_path)
    service = DocumentTranslationService(config=config, llm=MockLLMClient(prefix="[EN] "))
    calls: list[str] = []

    def fake_translate(input_path: Path, options: TranslationOptions) -> JobResult:
        calls.append(options.job_id)
        status = JobStatus.FAILED if options.job_id == "job-b" else JobStatus.COMPLETED
        return JobResult(
            job_id=options.job_id,
            status=status,
            artifacts=ArtifactPaths(),
            metadata=JobMetadata(job_id=options.job_id, source_file=input_path.name),
            error_message="failed" if status == JobStatus.FAILED else None,
        )

    service.translate = fake_translate  # type: ignore[method-assign]

    batch = service.translate_batch(
        [
            (doc_a, TranslationOptions(job_id="job-a")),
            (doc_b, TranslationOptions(job_id="job-b")),
        ]
    )

    assert calls == ["job-a", "job-b"]
    assert batch.status == JobStatus.FAILED
    assert [job.status for job in batch.jobs] == [JobStatus.COMPLETED, JobStatus.FAILED]
