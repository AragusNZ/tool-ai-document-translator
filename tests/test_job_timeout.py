from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from document_translator.cli import main
from document_translator.config.settings import PipelineConfig
from document_translator.errors import IssueCode, JobCancelledError
from document_translator.lib.llm.mock import MockLLMClient
from document_translator.models import TranslationOptions
from document_translator.pipeline import DocumentTranslationService
from document_translator.types import JobStatus, PipelineStage, TranslationMode


def test_cli_check_json_ready(tmp_path: Path) -> None:
    with patch("document_translator.cli.run_preflight_checks") as mock_checks:
        from document_translator.lib.preflight import CheckStatus, PreflightCheck, PreflightResult

        mock_checks.return_value = PreflightResult(
            checks=[
                PreflightCheck(name="pandoc", status=CheckStatus.OK, message="ok"),
            ]
        )
        code = main(["check", "--format", "json", "--output-dir", str(tmp_path)])

    assert code == 0


def test_cli_check_not_ready(tmp_path: Path) -> None:
    with patch("document_translator.cli.run_preflight_checks") as mock_checks:
        from document_translator.lib.preflight import CheckStatus, PreflightCheck, PreflightResult

        mock_checks.return_value = PreflightResult(
            checks=[
                PreflightCheck(
                    name="llm_api_key",
                    status=CheckStatus.FAIL,
                    message="CURSOR_API_KEY is not set",
                ),
            ]
        )
        code = main(["check", "--output-dir", str(tmp_path)])

    assert code == 1


def test_cli_invalid_timeout(tmp_path: Path) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")
    code = main(
        [
            "translate",
            str(doc),
            "--job-id",
            "bad-timeout",
            "--output-dir",
            str(tmp_path / "runs"),
            "--timeout",
            "0",
        ]
    )
    assert code == 1


@pytest.mark.integration
def test_pipeline_job_timeout_writes_failed_status(spanish_contract: Path, tmp_path: Path) -> None:
    config = PipelineConfig(
        runs_dir=tmp_path,
        job_timeout_seconds=0.001,
        chunk_size=500,
    )
    service = DocumentTranslationService(config=config, llm=MockLLMClient(prefix="[EN] "))

    with patch("document_translator.pipeline.export_markdown"):
        times = iter([0.0, 0.0, 0.0] + [10.0] * 100)
        with patch(
            "document_translator.lib.job_control.time.monotonic",
            side_effect=lambda: next(times),
        ):
            result = service.translate(
                spanish_contract,
                TranslationOptions(
                    job_id="timeout-job",
                    translation_mode=TranslationMode.QUICK,
                ),
            )

    assert result.status == JobStatus.FAILED
    assert result.error_code == IssueCode.JOB_TIMEOUT
    status = json.loads((tmp_path / "timeout-job" / "status.json").read_text(encoding="utf-8"))
    assert status["terminal_status"] == "failed"
    assert status["error_code"] == IssueCode.JOB_TIMEOUT.value
    assert status["elapsed_seconds"] is not None
    assert status["job_timeout_seconds"] == 0.001


@pytest.mark.integration
def test_pipeline_request_job_cancel(spanish_contract: Path, tmp_path: Path) -> None:
    from document_translator.extract.common import extract_single_file
    from document_translator.lib.job_control import request_job_cancel

    config = PipelineConfig(runs_dir=tmp_path, chunk_size=500)
    service = DocumentTranslationService(config=config, llm=MockLLMClient(prefix="[EN] "))

    def _extract_then_cancel(*args, **kwargs):  # noqa: ANN002, ANN003
        result = extract_single_file(*args, **kwargs)
        request_job_cancel()
        return result

    with patch("document_translator.pipeline.export_markdown"):
        with patch("document_translator.pipeline.extract_single_file", side_effect=_extract_then_cancel):
            result = service.translate(
                spanish_contract,
                TranslationOptions(job_id="signal-cancel", translation_mode=TranslationMode.QUICK),
            )

    assert result.status == JobStatus.FAILED
    assert result.error_code == IssueCode.JOB_CANCELLED
    status = json.loads((tmp_path / "signal-cancel" / "status.json").read_text(encoding="utf-8"))
    assert status["terminal_status"] == "failed"
    assert status["error_code"] == IssueCode.JOB_CANCELLED.value


@pytest.mark.integration
def test_pipeline_job_cancelled(spanish_contract: Path, tmp_path: Path) -> None:
    config = PipelineConfig(runs_dir=tmp_path, chunk_size=500)
    service = DocumentTranslationService(config=config, llm=MockLLMClient(prefix="[EN] "))

    def _raise_cancelled(*args, **kwargs):  # noqa: ANN002, ANN003
        raise JobCancelledError(stage=PipelineStage.TRANSLATING)

    with patch("document_translator.pipeline.export_markdown"):
        with patch("document_translator.pipeline.translate_source_chunks", side_effect=_raise_cancelled):
            result = service.translate(
                spanish_contract,
                TranslationOptions(job_id="cancel-job", translation_mode=TranslationMode.QUICK),
            )

    assert result.status == JobStatus.FAILED
    assert result.error_code == IssueCode.JOB_CANCELLED
