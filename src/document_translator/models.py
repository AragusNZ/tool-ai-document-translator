from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from document_translator.config.defaults import DEFAULT_LLM_SELECTOR, DEFAULT_TARGET_LANG
from document_translator.config.formats import ExportFormat
from document_translator.errors import IssueCode, PipelineIssue
from document_translator.types import JobStatus, PipelineStage, TranslationMode


class ExtractionAlert(BaseModel):
    code: str
    severity: str = "warn"
    message: str
    scope: dict[str, str] = Field(default_factory=dict)


class DiscrepancySeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    BREAKING = "breaking"


class Discrepancy(BaseModel):
    chunk_index: int
    sentence_index: int
    translation_1: str
    translation_2: str
    source_span: str = ""
    equivalent: bool = False
    severity: DiscrepancySeverity = DiscrepancySeverity.LOW
    explanation: str = ""
    resolved: bool = False
    resolution: str = ""
    chosen_variant: str = ""


class JobSummary(BaseModel):
    headline: str
    warnings: list[str] = Field(default_factory=list)
    review_items: list[str] = Field(default_factory=list)


class LLMUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float | None = None


class ArtifactPaths(BaseModel):
    final_output: Path | None = None
    metadata_json: Path | None = None
    status_json: Path | None = None


class JobMetadata(BaseModel):
    job_id: str
    source_file: str
    source_lang: str | None = None
    source_lang_confidence: float | None = None
    source_lang_override: bool = False
    target_lang: str = DEFAULT_TARGET_LANG
    translation_mode: str = TranslationMode.QUICK.value
    translation_context: str | None = None
    is_legal_document: bool = False
    skipped_translation: bool = False
    model: str = DEFAULT_LLM_SELECTOR
    page_count: int | None = None
    chunk_count: int = 0
    extraction_alerts: list[ExtractionAlert] = Field(default_factory=list)
    conversion_method: str | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    job_timeout_seconds: float | None = None
    llm_call_count: int = 0
    llm_usage: LLMUsage = Field(default_factory=LLMUsage)
    discrepancy_count: int = 0
    unresolved_breaking_count: int = 0
    issues: list[PipelineIssue] = Field(default_factory=list)
    failed_stage: PipelineStage | None = None
    error_code: IssueCode | None = None
    error_message: str | None = None
    lang_used_ai: bool = False
    legal_used_ai: bool = False
    export_format: str | None = None
    final_exported: bool = False
    summary: JobSummary | None = None
    discrepancies: list[Discrepancy] = Field(default_factory=list)
    artifact_availability: dict[str, bool] = Field(default_factory=dict)
    job_status: JobStatus | None = None


class JobResult(BaseModel):
    job_id: str
    status: JobStatus
    artifacts: ArtifactPaths
    metadata: JobMetadata
    discrepancies: list[Discrepancy] = Field(default_factory=list)
    error_message: str | None = None
    error_code: IssueCode | None = None
    failed_stage: PipelineStage | None = None

    def model_dump_json_api(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status.value,
            "artifacts": {k: str(v) if v else None for k, v in self.artifacts.model_dump().items()},
            "artifact_availability": self.metadata.artifact_availability,
            "metadata": self.metadata.model_dump(mode="json"),
            "issues": [i.model_dump(mode="json") for i in self.metadata.issues],
            "discrepancies": [d.model_dump(mode="json") for d in self.discrepancies],
            "discrepancy_count": len(self.discrepancies),
            "unresolved_breaking_count": self.metadata.unresolved_breaking_count,
            "error_message": self.error_message,
            "error_code": self.error_code.value if self.error_code else None,
            "failed_stage": self.failed_stage.value if self.failed_stage else None,
        }


def aggregate_job_status(jobs: list[JobResult]) -> JobStatus:
    if any(job.status == JobStatus.FAILED for job in jobs):
        return JobStatus.FAILED
    if any(job.status == JobStatus.COMPLETED_WITH_WARNINGS for job in jobs):
        return JobStatus.COMPLETED_WITH_WARNINGS
    return JobStatus.COMPLETED


class BatchJobResult(BaseModel):
    jobs: list[JobResult]
    status: JobStatus

    def model_dump_json_api(self) -> dict[str, Any]:
        completed_count = sum(1 for job in self.jobs if job.status == JobStatus.COMPLETED)
        failed_count = sum(1 for job in self.jobs if job.status == JobStatus.FAILED)
        warnings_count = sum(
            1 for job in self.jobs if job.status == JobStatus.COMPLETED_WITH_WARNINGS
        )
        return {
            "status": self.status.value,
            "job_count": len(self.jobs),
            "completed_count": completed_count,
            "failed_count": failed_count,
            "completed_with_warnings_count": warnings_count,
            "jobs": [job.model_dump_json_api() for job in self.jobs],
        }


class TranslationOptions(BaseModel):
    job_id: str = Field(default_factory=lambda: str(uuid4()))
    force_overwrite: bool = False
    source_lang: str | None = None
    target_lang: str = DEFAULT_TARGET_LANG
    export_format: ExportFormat | None = None
    translation_mode: TranslationMode = TranslationMode.QUICK
    translation_context: str | None = None

    @field_validator("translation_context", mode="before")
    @classmethod
    def _normalize_translation_context(cls, value: object) -> str | None:
        from document_translator.translate.service import normalize_translation_context

        if value is None:
            return None
        return normalize_translation_context(str(value))

    @field_validator("translation_mode", mode="before")
    @classmethod
    def _normalize_translation_mode(cls, value: object) -> TranslationMode:
        if value is None:
            return TranslationMode.QUICK
        if isinstance(value, TranslationMode):
            return value
        try:
            return TranslationMode(str(value))
        except ValueError as exc:
            raise ValueError(
                f"Invalid translation mode: {value!r}. Use 'quick' or 'thorough'."
            ) from exc

    @field_validator("source_lang", mode="before")
    @classmethod
    def _normalize_source_lang(cls, value: object) -> str | None:
        from document_translator.config.languages import normalize_lang_code

        if value is None:
            return None
        return normalize_lang_code(str(value))

    @field_validator("target_lang", mode="before")
    @classmethod
    def _normalize_target_lang(cls, value: object) -> str:
        from document_translator.config.languages import normalize_lang_code

        if value is None:
            return DEFAULT_TARGET_LANG
        return normalize_lang_code(str(value))
