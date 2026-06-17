from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from document_translator.cli import main
from document_translator.lib.llm import MockLLMClient

JOB_RESULT_API_KEYS = {
    "job_id",
    "status",
    "artifacts",
    "artifact_availability",
    "metadata",
    "issues",
    "discrepancies",
    "discrepancy_count",
    "unresolved_breaking_count",
    "error_message",
    "error_code",
    "failed_stage",
}

BATCH_RESULT_API_KEYS = {
    "status",
    "job_count",
    "completed_count",
    "failed_count",
    "completed_with_warnings_count",
    "jobs",
}


def _assert_job_result_api(payload: dict[str, object]) -> None:
    assert JOB_RESULT_API_KEYS <= set(payload.keys())
    assert payload["status"] == "completed"
    availability = payload["artifact_availability"]
    assert isinstance(availability, dict)
    assert availability.get("status_json") is True
    assert availability.get("metadata_json") is True
    artifacts = payload["artifacts"]
    assert isinstance(artifacts, dict)
    assert "resolved_md" in artifacts
    assert "resolved_md" in availability


@pytest.mark.integration
def test_cli_json_success_real_service(
    spanish_contract: Path,
    tmp_path: Path,
    touch_export,
    capsys: pytest.CaptureFixture[str],
) -> None:
    mock = MockLLMClient(prefix="[EN] ")
    runs = tmp_path / "runs"

    with (
        patch("document_translator.pipeline.build_llm_client", return_value=mock),
        patch("document_translator.pipeline.export_markdown", side_effect=touch_export),
    ):
        code = main(
            [
                "translate",
                str(spanish_contract),
                "--job-id",
                "cli-json-success",
                "--output-dir",
                str(runs),
                "--format",
                "json",
            ]
        )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["job_id"] == "cli-json-success"
    _assert_job_result_api(payload)
    assert payload["metadata"]["source_lang"] == "es"


@pytest.mark.integration
def test_cli_json_failure_real_service(
    spanish_contract: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    mock = MockLLMClient()

    def fail_translate(system: str, user: str) -> str:
        if "Chunk" in user:
            raise RuntimeError("LLM down")
        return "es"

    mock.complete = fail_translate  # type: ignore[method-assign]
    runs = tmp_path / "runs"

    with (
        patch("document_translator.pipeline.build_llm_client", return_value=mock),
        patch("document_translator.pipeline.export_markdown"),
    ):
        code = main(
            [
                "translate",
                str(spanish_contract),
                "--job-id",
                "cli-json-fail",
                "--output-dir",
                str(runs),
                "--format",
                "json",
            ]
        )

    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"
    assert payload["error_message"]
    assert payload["error_code"] is not None
    assert JOB_RESULT_API_KEYS <= set(payload.keys())


@pytest.mark.integration
def test_cli_json_warnings_real_service(
    spanish_contract: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    mock = MockLLMClient(prefix="[EN] ")
    runs = tmp_path / "runs"

    with (
        patch("document_translator.pipeline.build_llm_client", return_value=mock),
        patch(
            "document_translator.pipeline.export_markdown",
            side_effect=RuntimeError("pandoc failed"),
        ),
    ):
        code = main(
            [
                "translate",
                str(spanish_contract),
                "--job-id",
                "cli-json-warn",
                "--output-dir",
                str(runs),
                "--format",
                "json",
                "--export-format",
                "pdf",
            ]
        )

    assert code == 3
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "completed_with_warnings"
    assert payload["artifact_availability"]["final_output"] is False


@pytest.mark.integration
def test_cli_batch_json_envelope(
    spanish_contract: Path,
    tmp_path: Path,
    touch_export,
    capsys: pytest.CaptureFixture[str],
) -> None:
    doc_b = tmp_path / "contract-b.txt"
    doc_b.write_text(spanish_contract.read_text(encoding="utf-8"), encoding="utf-8")
    mock = MockLLMClient(prefix="[EN] ")
    runs = tmp_path / "runs"

    with (
        patch("document_translator.pipeline.build_llm_client", return_value=mock),
        patch("document_translator.pipeline.export_markdown", side_effect=touch_export),
    ):
        code = main(
            [
                "translate",
                str(spanish_contract),
                str(doc_b),
                "--job-ids",
                "batch-a",
                "batch-b",
                "--output-dir",
                str(runs),
                "--format",
                "json",
            ]
        )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert BATCH_RESULT_API_KEYS <= set(payload.keys())
    assert payload["job_count"] == 2
    assert payload["completed_count"] == 2
    assert payload["failed_count"] == 0
    assert len(payload["jobs"]) == 2
    for job in payload["jobs"]:
        _assert_job_result_api(job)


@pytest.mark.integration
def test_cli_writes_status_and_metadata(
    spanish_contract: Path,
    tmp_path: Path,
    touch_export,
) -> None:
    mock = MockLLMClient(prefix="[EN] ")
    runs = tmp_path / "runs"
    job_id = "cli-artifacts"

    with (
        patch("document_translator.pipeline.build_llm_client", return_value=mock),
        patch("document_translator.pipeline.export_markdown", side_effect=touch_export),
    ):
        code = main(
            [
                "translate",
                str(spanish_contract),
                "--job-id",
                job_id,
                "--output-dir",
                str(runs),
                "--format",
                "json",
            ]
        )

    assert code == 0
    status_path = runs / job_id / "status.json"
    metadata_path = runs / job_id / "metadata.json"
    assert status_path.exists()
    assert metadata_path.exists()
    status = json.loads(status_path.read_text(encoding="utf-8"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert status["status"] == "terminal"
    assert status["terminal_status"] == "completed"
    assert metadata["job_id"] == job_id
