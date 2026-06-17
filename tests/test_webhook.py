from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from document_translator.cli import main
from document_translator.config.settings import PipelineConfig
from document_translator.errors import IssueCode
from document_translator.lib.llm.mock import MockLLMClient
from document_translator.lib.webhook import (
    build_terminal_webhook_payload,
    deliver_terminal_webhook,
    sign_webhook_body,
)
from document_translator.models import ArtifactPaths, JobMetadata, JobResult, TranslationOptions
from document_translator.pipeline import DocumentTranslationService
from document_translator.types import JobStatus, TranslationMode


def test_sign_webhook_body() -> None:
    body = b'{"event":"job.terminal"}'
    assert sign_webhook_body(body, "secret").startswith("sha256=")
    assert sign_webhook_body(body, "secret") != sign_webhook_body(body, "other")


def test_build_terminal_webhook_payload() -> None:
    result = JobResult(
        job_id="j1",
        status=JobStatus.COMPLETED,
        artifacts=ArtifactPaths(),
        metadata=JobMetadata(job_id="j1", source_file="doc.txt"),
    )
    payload = build_terminal_webhook_payload(result)
    assert payload["event"] == "job.terminal"
    assert payload["job"]["job_id"] == "j1"
    assert payload["job"]["status"] == "completed"


def test_deliver_terminal_webhook_posts_json() -> None:
    result = JobResult(
        job_id="j1",
        status=JobStatus.COMPLETED,
        artifacts=ArtifactPaths(),
        metadata=JobMetadata(job_id="j1", source_file="doc.txt"),
    )
    captured: dict[str, object] = {}

    def _fake_urlopen(request, timeout=0):  # noqa: ANN001, ARG001
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = request.data
        response = MagicMock()
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        response.status = 200
        response.getcode.return_value = 200
        return response

    with patch("document_translator.lib.webhook.urllib.request.urlopen", side_effect=_fake_urlopen):
        deliver_terminal_webhook("https://8.8.8.8/hook", result, secret="top-secret")

    assert captured["url"] == "https://8.8.8.8/hook"
    body = captured["body"]
    assert isinstance(body, bytes)
    payload = json.loads(body)
    assert payload["event"] == "job.terminal"
    headers = captured["headers"]
    assert headers["Content-type"] == "application/json"
    signature = headers["X-document-translator-signature"]
    assert signature == sign_webhook_body(body, "top-secret")


def test_deliver_terminal_webhook_http_error() -> None:
    import urllib.error

    result = JobResult(
        job_id="j1",
        status=JobStatus.FAILED,
        artifacts=ArtifactPaths(),
        metadata=JobMetadata(job_id="j1", source_file="doc.txt"),
    )

    with patch(
        "document_translator.lib.webhook.urllib.request.urlopen",
        side_effect=urllib.error.HTTPError("https://8.8.8.8/hook", 500, "error", {}, BytesIO(b"")),
    ):
        with pytest.raises(RuntimeError, match="HTTP 500"):
            deliver_terminal_webhook("https://8.8.8.8/hook", result)


def test_cli_invalid_webhook_url(tmp_path: Path) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")
    code = main(
        [
            "translate",
            str(doc),
            "--job-id",
            "bad-webhook",
            "--output-dir",
            str(tmp_path / "runs"),
            "--webhook-url",
            "ftp://example.com/hook",
        ]
    )
    assert code == 1


@pytest.mark.integration
def test_pipeline_webhook_on_terminal_status(spanish_contract: Path, tmp_path: Path) -> None:
    config = PipelineConfig(
        runs_dir=tmp_path,
        webhook_url="https://8.8.8.8/hook",
        webhook_secret="secret",
        chunk_size=500,
    )
    service = DocumentTranslationService(config=config, llm=MockLLMClient(prefix="[EN] "))
    delivered: list[JobResult] = []

    def _capture(url: str, result: JobResult, **kwargs):  # noqa: ANN003
        delivered.append(result)

    with patch("document_translator.pipeline.export_markdown"):
        with patch("document_translator.pipeline.deliver_terminal_webhook", side_effect=_capture):
            result = service.translate(
                spanish_contract,
                TranslationOptions(job_id="webhook-job", translation_mode=TranslationMode.QUICK),
            )

    assert result.status == JobStatus.COMPLETED
    assert len(delivered) == 1
    assert delivered[0].job_id == "webhook-job"


@pytest.mark.integration
def test_pipeline_webhook_failure_records_warning(spanish_contract: Path, tmp_path: Path) -> None:
    config = PipelineConfig(
        runs_dir=tmp_path,
        webhook_url="https://8.8.8.8/hook",
        chunk_size=500,
    )
    service = DocumentTranslationService(config=config, llm=MockLLMClient(prefix="[EN] "))

    with patch("document_translator.pipeline.export_markdown"):
        with patch(
            "document_translator.pipeline.deliver_terminal_webhook",
            side_effect=RuntimeError("connection refused"),
        ):
            result = service.translate(
                spanish_contract,
                TranslationOptions(job_id="webhook-fail", translation_mode=TranslationMode.QUICK),
            )

    assert result.status == JobStatus.COMPLETED_WITH_WARNINGS
    assert any(issue.code == IssueCode.WEBHOOK_FAILED for issue in result.metadata.issues)
    metadata_payload = json.loads((tmp_path / "webhook-fail" / "metadata.json").read_text(encoding="utf-8"))
    assert any(issue["code"] == IssueCode.WEBHOOK_FAILED.value for issue in metadata_payload["issues"])
    status_payload = json.loads((tmp_path / "webhook-fail" / "status.json").read_text(encoding="utf-8"))
    assert status_payload["terminal_status"] == JobStatus.COMPLETED_WITH_WARNINGS.value
    assert status_payload["issue_count"] >= 1
