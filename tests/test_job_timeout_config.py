from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from document_translator.cli import main
from document_translator.config.settings import PipelineConfig
from document_translator.lib.llm.mock import MockLLMClient
from document_translator.models import TranslationOptions
from document_translator.pipeline import DocumentTranslationService
from document_translator.types import JobStatus, TranslationMode


def test_pipeline_config_job_timeout_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOCUMENT_TRANSLATOR_JOB_TIMEOUT", "7200")
    config = PipelineConfig()
    assert config.job_timeout_seconds == 7200.0


def test_pipeline_config_job_timeout_from_job_timeout_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DOCUMENT_TRANSLATOR_JOB_TIMEOUT", raising=False)
    monkeypatch.setenv("JOB_TIMEOUT", "900")
    config = PipelineConfig()
    assert config.job_timeout_seconds == 900.0


def test_cli_timeout_overrides_config_json(tmp_path: Path) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"job_timeout_seconds": 120}), encoding="utf-8")
    captured: dict[str, object] = {}

    class FakeService:
        def __init__(self, config: PipelineConfig) -> None:
            captured["job_timeout_seconds"] = config.job_timeout_seconds

        def translate(self, input_path: Path, options):  # noqa: ANN001
            from document_translator.models import ArtifactPaths, JobMetadata, JobResult

            return JobResult(
                job_id="timeout-cli",
                status=JobStatus.COMPLETED,
                artifacts=ArtifactPaths(),
                metadata=JobMetadata(job_id="timeout-cli", source_file="doc.txt"),
            )

    with patch("document_translator.cli.DocumentTranslationService", FakeService):
        code = main(
            [
                "translate",
                str(doc),
                "--job-id",
                "timeout-cli",
                "--output-dir",
                str(tmp_path / "runs"),
                "--config",
                str(config_path),
                "--timeout",
                "45",
            ]
        )

    assert code == 0
    assert captured["job_timeout_seconds"] == 45.0


@pytest.mark.integration
def test_job_timeout_recorded_in_metadata_and_status(spanish_contract: Path, tmp_path: Path) -> None:
    config = PipelineConfig(
        runs_dir=tmp_path,
        job_timeout_seconds=3600,
        chunk_size=500,
    )
    service = DocumentTranslationService(config=config, llm=MockLLMClient(prefix="[EN] "))

    with patch("document_translator.pipeline.export_markdown"):
        result = service.translate(
            spanish_contract,
            TranslationOptions(
                job_id="timeout-meta",
                translation_mode=TranslationMode.QUICK,
            ),
        )

    assert result.status == JobStatus.COMPLETED
    assert result.metadata.job_timeout_seconds == 3600
    status = json.loads((tmp_path / "timeout-meta" / "status.json").read_text(encoding="utf-8"))
    assert status["job_timeout_seconds"] == 3600
    assert status["elapsed_seconds"] is not None
    assert result.metadata.duration_seconds is not None
