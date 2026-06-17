from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from document_translator.config.settings import PipelineConfig
from document_translator.lib.llm import MockLLMClient
from document_translator.models import (
    ArtifactPaths,
    BatchJobResult,
    JobMetadata,
    JobResult,
    TranslationOptions,
    aggregate_job_status,
)
from document_translator.pipeline import DocumentTranslationService
from document_translator.types import JobStatus, TranslationMode


def test_pipeline_config_resolve_runs_dir_relative(tmp_path: Path) -> None:
    config = PipelineConfig(runs_dir=Path("runs"), root=tmp_path)
    assert config.resolve_runs_dir() == tmp_path / "runs"


def test_pipeline_config_resolve_runs_dir_absolute(tmp_path: Path) -> None:
    abs_runs = tmp_path / "absolute-runs"
    config = PipelineConfig(runs_dir=abs_runs, root=tmp_path / "other")
    assert config.resolve_runs_dir() == abs_runs


def test_job_result_model_dump_json_api_fields() -> None:
    metadata = JobMetadata(job_id="j1", source_file="doc.txt", source_lang="de", target_lang="fr")
    result = JobResult(
        job_id="j1",
        status=JobStatus.COMPLETED,
        artifacts=ArtifactPaths(),
        metadata=metadata,
    )
    api = result.model_dump_json_api()
    assert api["job_id"] == "j1"
    assert api["status"] == "completed"
    assert api["metadata"]["source_lang"] == "de"
    assert api["metadata"]["target_lang"] == "fr"
    assert "artifacts" in api
    assert "issues" in api


def test_translation_options_normalizes_target_lang() -> None:
    opts = TranslationOptions(target_lang="FR")
    assert opts.target_lang == "fr"


def test_translation_options_rejects_invalid_target_lang() -> None:
    with pytest.raises(ValidationError):
        TranslationOptions(target_lang="french")


def test_translation_options_defaults_to_quick_mode() -> None:
    opts = TranslationOptions()
    assert opts.translation_mode == TranslationMode.QUICK


def test_translation_options_accepts_thorough_mode() -> None:
    opts = TranslationOptions(translation_mode=TranslationMode.THOROUGH)
    assert opts.translation_mode == TranslationMode.THOROUGH


def test_translation_options_accepts_thorough_mode_string() -> None:
    opts = TranslationOptions(translation_mode="thorough")
    assert opts.translation_mode == TranslationMode.THOROUGH


def test_translation_options_rejects_invalid_translation_mode() -> None:
    with pytest.raises(ValidationError):
        TranslationOptions(translation_mode="fast")


def test_aggregate_job_status_failed_wins() -> None:
    jobs = [
        JobResult(
            job_id="ok",
            status=JobStatus.COMPLETED,
            artifacts=ArtifactPaths(),
            metadata=JobMetadata(job_id="ok", source_file="a.txt"),
        ),
        JobResult(
            job_id="bad",
            status=JobStatus.FAILED,
            artifacts=ArtifactPaths(),
            metadata=JobMetadata(job_id="bad", source_file="b.txt"),
        ),
    ]
    assert aggregate_job_status(jobs) == JobStatus.FAILED


def test_aggregate_job_status_warnings_without_failure() -> None:
    jobs = [
        JobResult(
            job_id="ok",
            status=JobStatus.COMPLETED,
            artifacts=ArtifactPaths(),
            metadata=JobMetadata(job_id="ok", source_file="a.txt"),
        ),
        JobResult(
            job_id="warn",
            status=JobStatus.COMPLETED_WITH_WARNINGS,
            artifacts=ArtifactPaths(),
            metadata=JobMetadata(job_id="warn", source_file="b.txt"),
        ),
    ]
    assert aggregate_job_status(jobs) == JobStatus.COMPLETED_WITH_WARNINGS


def test_batch_job_result_model_dump_json_api() -> None:
    batch = BatchJobResult(
        jobs=[
            JobResult(
                job_id="j1",
                status=JobStatus.COMPLETED,
                artifacts=ArtifactPaths(),
                metadata=JobMetadata(job_id="j1", source_file="a.txt"),
            ),
            JobResult(
                job_id="j2",
                status=JobStatus.FAILED,
                artifacts=ArtifactPaths(),
                metadata=JobMetadata(job_id="j2", source_file="b.txt"),
            ),
        ],
        status=JobStatus.FAILED,
    )
    api = batch.model_dump_json_api()
    assert api["status"] == "failed"
    assert api["job_count"] == 2
    assert api["completed_count"] == 1
    assert api["failed_count"] == 1
    assert api["completed_with_warnings_count"] == 0
    assert [job["job_id"] for job in api["jobs"]] == ["j1", "j2"]


def test_translate_batch_requires_items(tmp_path: Path) -> None:
    config = PipelineConfig(runs_dir=tmp_path / "runs", root=tmp_path)
    service = DocumentTranslationService(config=config, llm=MockLLMClient(prefix="[EN] "))

    with pytest.raises(ValueError, match="at least one input"):
        service.translate_batch([])