from __future__ import annotations

from pathlib import Path

from document_translator.config.formats import ExportFormat
from document_translator.storage.paths import JobPaths
from document_translator.types import JobStatus, PipelineStage


def test_job_paths_ensure_dirs(tmp_path: Path) -> None:
    paths = JobPaths(tmp_path / "runs", "job-1", export_format=ExportFormat.PDF)
    paths.ensure_dirs()
    assert paths.input_dir.is_dir()
    assert paths.artifacts_dir.is_dir()


def test_job_paths_artifact_properties(tmp_path: Path) -> None:
    paths = JobPaths(tmp_path / "runs", "job-1", export_format=ExportFormat.PDF)
    assert paths.extracted_md.name == "01-extracted.md"
    assert paths.translation_1_md.name == "02-translation-1.md"
    assert paths.resolved_md.name == "04-resolved.md"
    assert paths.final_output.name == "05-final.pdf"


def test_job_paths_final_output_respects_export_format(tmp_path: Path) -> None:
    paths = JobPaths(tmp_path / "runs", "job-docx", export_format=ExportFormat.DOCX)
    assert paths.final_output.name == "05-final.docx"


def test_to_artifact_paths_terminal(tmp_path: Path) -> None:
    paths = JobPaths(tmp_path / "runs", "job-1", export_format=ExportFormat.PDF)
    paths.ensure_dirs()
    paths.final_output.write_text("final", encoding="utf-8")
    paths.metadata_json.write_text("{}", encoding="utf-8")
    artifacts = paths.to_artifact_paths()
    assert artifacts.final_output == paths.final_output
    assert artifacts.metadata_json == paths.metadata_json
    assert artifacts.status_json == paths.status_json


def test_cleanup_working_files(tmp_path: Path) -> None:
    paths = JobPaths(tmp_path / "runs", "job-1", export_format=ExportFormat.PDF)
    paths.ensure_dirs()
    paths.input_dir.mkdir(parents=True, exist_ok=True)
    paths.extracted_md.write_text("x", encoding="utf-8")
    paths.resolved_md.write_text("y", encoding="utf-8")
    paths.final_output.write_text("final", encoding="utf-8")
    paths.cleanup_working_files()
    assert not paths.extracted_md.exists()
    assert not paths.resolved_md.exists()
    assert paths.final_output.exists()


def test_cleanup_respects_keep_work_files(tmp_path: Path) -> None:
    paths = JobPaths(tmp_path / "runs", "job-keep", export_format=ExportFormat.PDF)
    paths.ensure_dirs()
    paths.extracted_md.write_text("x", encoding="utf-8")
    paths.combined_export_md.write_text("combined", encoding="utf-8")
    paths.cleanup_working_files(keep_work_files=True)
    assert paths.extracted_md.exists()
    assert paths.combined_export_md.exists()


def test_artifact_availability_terminal_keys(tmp_path: Path) -> None:
    paths = JobPaths(tmp_path / "runs", "job-avail", export_format=ExportFormat.PDF)
    paths.ensure_dirs()
    paths.final_output.write_text("final", encoding="utf-8")
    paths.metadata_json.write_text("{}", encoding="utf-8")
    paths.write_status(
        PipelineStage.COMPLETED,
        message="done",
        progress=1.0,
        issue_count=0,
        terminal_status=JobStatus.COMPLETED,
    )
    availability = paths.artifact_availability()
    assert set(availability.keys()) == {"final_output", "metadata_json", "status_json"}
    assert all(availability.values())


def test_cleanup_removes_legacy_artifact_paths(tmp_path: Path) -> None:
    paths = JobPaths(tmp_path / "runs", "job-legacy", export_format=ExportFormat.PDF)
    paths.ensure_dirs()
    paths.results_md.write_text("old report", encoding="utf-8")
    paths.discrepancies_json.write_text("[]", encoding="utf-8")
    paths.cleanup_working_files()
    assert not paths.results_md.exists()
    assert not paths.discrepancies_json.exists()


def test_write_status_terminal(tmp_path: Path) -> None:
    paths = JobPaths(tmp_path / "runs", "job-1", export_format=ExportFormat.PDF)
    paths.ensure_dirs()
    paths.write_status(
        PipelineStage.COMPLETED,
        message="done",
        progress=1.0,
        issue_count=2,
        terminal_status=JobStatus.COMPLETED,
    )
    import json

    payload = json.loads(paths.status_json.read_text())
    assert payload["status"] == "terminal"
    assert payload["terminal_status"] == "completed"
    assert payload["issue_count"] == 2
