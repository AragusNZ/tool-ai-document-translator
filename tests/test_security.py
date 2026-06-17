from __future__ import annotations

import json
import stat
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from document_translator.cli import main
from document_translator.config.settings import PipelineConfig
from document_translator.lib.subprocess.sanitize import sanitize_subprocess_detail
from document_translator.lib.validation import assert_safe_webhook_url, validate_job_id
from document_translator.lib.webhook import deliver_terminal_webhook
from document_translator.models import ArtifactPaths, JobMetadata, JobResult
from document_translator.types import JobStatus


def test_validate_job_id_rejects_path_traversal() -> None:
    with pytest.raises(ValueError, match="job_id must"):
        validate_job_id("../escape")


def test_assert_safe_webhook_url_blocks_literal_private_ip() -> None:
    with pytest.raises(ValueError, match="private or reserved"):
        assert_safe_webhook_url("http://127.0.0.1/hook")


def test_assert_safe_webhook_url_requires_https_when_enabled() -> None:
    with pytest.raises(ValueError, match="https"):
        assert_safe_webhook_url("http://8.8.8.8/hook", https_only=True)


def test_pipeline_config_rejects_private_webhook_from_config_json(tmp_path: Path) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"webhook_url": "http://127.0.0.1/hook"}), encoding="utf-8")

    code = main(
        [
            "translate",
            str(doc),
            "--job-id",
            "config-webhook",
            "--output-dir",
            str(tmp_path / "runs"),
            "--config",
            str(config_path),
        ]
    )
    assert code == 1


def test_cli_rejects_invalid_job_id(tmp_path: Path) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")
    code = main(
        [
            "translate",
            str(doc),
            "--job-id",
            "../escape",
            "--output-dir",
            str(tmp_path / "runs"),
        ]
    )
    assert code == 1


def test_cli_rejects_directory_input(tmp_path: Path) -> None:
    code = main(
        [
            "translate",
            str(tmp_path),
            "--job-id",
            "dir-input",
            "--output-dir",
            str(tmp_path / "runs"),
        ]
    )
    assert code == 1


def test_cli_rejects_symlink_input(tmp_path: Path) -> None:
    real = tmp_path / "real.txt"
    real.write_text("hello", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(real)

    code = main(
        [
            "translate",
            str(link),
            "--job-id",
            "symlink-input",
            "--output-dir",
            str(tmp_path / "runs"),
        ]
    )
    assert code == 1


def test_cli_rejects_oversized_input(tmp_path: Path) -> None:
    doc = tmp_path / "big.txt"
    doc.write_bytes(b"x" * 32)
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"max_input_bytes": 16}), encoding="utf-8")

    code = main(
        [
            "translate",
            str(doc),
            "--job-id",
            "oversized-input",
            "--output-dir",
            str(tmp_path / "runs"),
            "--config",
            str(config_path),
        ]
    )
    assert code == 1


def test_job_paths_use_restricted_permissions(tmp_path: Path) -> None:
    from document_translator.config.formats import ExportFormat
    from document_translator.storage.paths import JobPaths

    runs = tmp_path / "runs"
    paths = JobPaths(runs, "perm-job", export_format=ExportFormat.TXT)
    paths.ensure_dirs()

    assert stat.S_IMODE(paths.root.stat().st_mode) == 0o700


def test_sanitize_subprocess_detail_strips_paths() -> None:
    detail = sanitize_subprocess_detail("failed at /home/user/secret/doc.pdf with error")
    assert "/home/user" not in detail
    assert "<path>" in detail


def test_deliver_terminal_webhook_retries_before_success() -> None:
    result = JobResult(
        job_id="j1",
        status=JobStatus.COMPLETED,
        artifacts=ArtifactPaths(),
        metadata=JobMetadata(job_id="j1", source_file="doc.txt"),
    )
    attempts: list[int] = []

    def _fake_deliver(*_args, **_kwargs) -> None:
        attempts.append(1)
        if len(attempts) < 2:
            raise RuntimeError("webhook request failed: connection refused")

    with (
        patch("document_translator.lib.webhook._deliver_once", side_effect=_fake_deliver),
        patch("document_translator.lib.webhook.time.sleep"),
    ):
        deliver_terminal_webhook("https://8.8.8.8/hook", result, max_retries=2, retry_base_delay=0)

    assert len(attempts) == 2


def test_pipeline_config_webhook_https_only() -> None:
    with pytest.raises(ValidationError, match="https"):
        PipelineConfig(webhook_url="http://8.8.8.8/hook", webhook_https_only=True)
