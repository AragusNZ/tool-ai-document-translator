from __future__ import annotations

import json
from pathlib import Path

STATUS_JSON_TERMINAL_KEYS = {
    "job_id",
    "stage",
    "status",
    "terminal_status",
    "message",
    "progress",
    "issue_count",
    "error_code",
    "job_timeout_seconds",
    "elapsed_seconds",
    "updated_at",
}


def test_status_json_terminal_shape(tmp_path: Path) -> None:
    from document_translator.config.formats import ExportFormat
    from document_translator.storage.paths import JobPaths
    from document_translator.types import JobStatus, PipelineStage

    paths = JobPaths(tmp_path / "runs", "status-contract", export_format=ExportFormat.TXT)
    paths.ensure_dirs()
    paths.write_status(
        PipelineStage.EXPORTING,
        message="done",
        progress=1.0,
        issue_count=0,
        terminal_status=JobStatus.COMPLETED,
        job_timeout_seconds=60.0,
        elapsed_seconds=12.5,
    )

    payload = json.loads(paths.status_json.read_text(encoding="utf-8"))
    assert STATUS_JSON_TERMINAL_KEYS <= set(payload.keys())
    assert payload["status"] == "terminal"
    assert payload["terminal_status"] == "completed"
