from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from document_translator.config.formats import ExportFormat
from document_translator.errors import IssueCode
from document_translator.lib.validation import resolve_job_root
from document_translator.models import ArtifactPaths
from document_translator.types import JobStatus, PipelineStage


class JobPaths:
    def __init__(self, runs_dir: Path, job_id: str, *, export_format: ExportFormat) -> None:
        self.job_id = job_id
        self.export_format = export_format
        self.root = resolve_job_root(runs_dir, job_id)
        self.input_dir = self.root / "input"
        self.artifacts_dir = self.root / "artifacts"
        self.status_json = self.root / "status.json"
        self.metadata_json = self.root / "metadata.json"
        self.discrepancies_json = self.root / "discrepancies.json"

    def ensure_dirs(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.input_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    @property
    def extracted_md(self) -> Path:
        return self.artifacts_dir / "01-extracted.md"

    @property
    def extraction_layout_json(self) -> Path:
        return self.artifacts_dir / "01-extraction-layout.json"

    @property
    def screenshots_dir(self) -> Path:
        return self.artifacts_dir / "screenshots"

    @property
    def translation_1_md(self) -> Path:
        return self.artifacts_dir / "02-translation-1.md"

    @property
    def translation_2_md(self) -> Path:
        return self.artifacts_dir / "02-translation-2.md"

    @property
    def resolved_md(self) -> Path:
        return self.artifacts_dir / "04-resolved.md"

    @property
    def combined_export_md(self) -> Path:
        return self.artifacts_dir / ".combined-export.md"

    @property
    def final_output(self) -> Path:
        return self.artifacts_dir / f"05-final.{self.export_format.value}"

    @property
    def results_md(self) -> Path:
        return self.artifacts_dir / "results.md"

    def to_artifact_paths(self) -> ArtifactPaths:
        return ArtifactPaths(
            final_output=self.final_output if self.final_output.exists() else None,
            resolved_md=self.resolved_md if self.resolved_md.exists() else None,
            metadata_json=self.metadata_json,
            status_json=self.status_json,
        )

    def artifact_availability(self) -> dict[str, bool]:
        screenshots_available = (
            self.screenshots_dir.is_dir() and any(self.screenshots_dir.iterdir())
        )
        return {
            "final_output": self.final_output.exists(),
            "resolved_md": self.resolved_md.exists(),
            "metadata_json": self.metadata_json.exists(),
            "status_json": self.status_json.exists(),
            "extraction_layout_json": self.extraction_layout_json.exists(),
            "screenshots_dir": screenshots_available,
        }

    def working_file_paths(self) -> list[Path]:
        return [
            self.extracted_md,
            self.extraction_layout_json,
            self.translation_1_md,
            self.translation_2_md,
            self.resolved_md,
            self.combined_export_md,
            self.results_md,
            self.discrepancies_json,
        ]

    def working_file_dirs(self) -> list[Path]:
        return [self.screenshots_dir]

    def cleanup_working_files(self, *, keep_work_files: bool = False, keep_resolved: bool = False) -> None:
        if keep_work_files:
            return

        def _safe_unlink(path: Path) -> None:
            if path.exists() and path.is_file() and self.root in path.parents:
                path.unlink()

        for path in self.working_file_paths():
            if keep_resolved and path == self.resolved_md:
                continue
            _safe_unlink(path)

        for directory in self.working_file_dirs():
            if directory.exists() and self.root in directory.parents:
                shutil.rmtree(directory, ignore_errors=True)

        if self.input_dir.exists() and self.root in self.input_dir.parents:
            shutil.rmtree(self.input_dir, ignore_errors=True)

    def write_status(
        self,
        stage: PipelineStage | JobStatus,
        *,
        message: str = "",
        progress: float = 0.0,
        issue_count: int = 0,
        terminal_status: JobStatus | None = None,
        error_code: IssueCode | None = None,
        job_timeout_seconds: float | None = None,
        elapsed_seconds: float | None = None,
    ) -> None:
        in_progress = terminal_status is None
        payload = {
            "job_id": self.job_id,
            "stage": stage.value if isinstance(stage, PipelineStage) else stage.value,
            "status": "in_progress" if in_progress else "terminal",
            "terminal_status": terminal_status.value if terminal_status else None,
            "message": message,
            "progress": progress,
            "issue_count": issue_count,
            "error_code": error_code.value if error_code else None,
            "job_timeout_seconds": job_timeout_seconds,
            "elapsed_seconds": round(elapsed_seconds, 3) if elapsed_seconds is not None else None,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        tmp = self.status_json.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.status_json)

    def write_queued(self, *, job_timeout_seconds: float | None = None) -> None:
        self.write_status(
            JobStatus.QUEUED,
            message="Job queued",
            progress=0.0,
            job_timeout_seconds=job_timeout_seconds,
            elapsed_seconds=0.0 if job_timeout_seconds is not None else None,
        )
