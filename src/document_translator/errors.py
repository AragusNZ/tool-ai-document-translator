from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from document_translator.types import PipelineStage


class IssueSeverity(str, Enum):
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


class IssueCode(str, Enum):
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    EMPTY_EXTRACTION = "EMPTY_EXTRACTION"
    LOW_TEXT_DENSITY = "LOW_TEXT_DENSITY"
    LARGE_INPUT_FILE = "LARGE_INPUT_FILE"
    ENCODING_LOSS = "ENCODING_LOSS"
    CONVERSION_DEGRADED = "CONVERSION_DEGRADED"
    OCR_APPLIED = "OCR_APPLIED"
    OCR_UNAVAILABLE = "OCR_UNAVAILABLE"
    EXTRACT_OPTION_IGNORED = "EXTRACT_OPTION_IGNORED"
    EXPORT_FAILED = "EXPORT_FAILED"
    COVER_TRANSLATION_FAILED = "COVER_TRANSLATION_FAILED"
    LANGUAGE_LOW_CONFIDENCE = "LANGUAGE_LOW_CONFIDENCE"
    LEGAL_CLASSIFICATION_AI = "LEGAL_CLASSIFICATION_AI"
    LLM_RESPONSE_PARSE_FAILED = "LLM_RESPONSE_PARSE_FAILED"
    CHUNK_COUNT_MISMATCH = "CHUNK_COUNT_MISMATCH"
    PIPELINE_FAILED = "PIPELINE_FAILED"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    JOB_TIMEOUT = "JOB_TIMEOUT"
    JOB_CANCELLED = "JOB_CANCELLED"
    SOURCE_LANG_MISMATCH = "SOURCE_LANG_MISMATCH"
    WEBHOOK_FAILED = "WEBHOOK_FAILED"


class PipelineIssue(BaseModel):
    code: IssueCode
    severity: IssueSeverity
    message: str
    stage: PipelineStage | None = None
    scope: dict[str, str] = Field(default_factory=dict)


class PipelineError(Exception):
    """Expected pipeline failure with structured context."""

    def __init__(
        self,
        message: str,
        *,
        code: IssueCode,
        stage: PipelineStage,
        cause: Exception | None = None,
        scope: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.stage = stage
        self.cause = cause
        self.scope = scope or {}


class UnsupportedFormatError(PipelineError):
    def __init__(self, suffix: str) -> None:
        super().__init__(
            f"Unsupported file type: {suffix}",
            code=IssueCode.UNSUPPORTED_FORMAT,
            stage=PipelineStage.EXTRACTING,
            scope={"suffix": suffix},
        )


class ChunkCountMismatchError(PipelineError):
    def __init__(self, pass1: int, pass2: int) -> None:
        super().__init__(
            f"Translation pass chunk count mismatch: pass1={pass1}, pass2={pass2}",
            code=IssueCode.CHUNK_COUNT_MISMATCH,
            stage=PipelineStage.TRANSLATING,
            scope={"pass1": str(pass1), "pass2": str(pass2)},
        )


class ConfigurationError(PipelineError):
    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            code=IssueCode.CONFIGURATION_ERROR,
            stage=PipelineStage.EXTRACTING,
        )


class JobTimeoutError(PipelineError):
    def __init__(self, *, stage: PipelineStage, timeout_seconds: float) -> None:
        super().__init__(
            f"Job exceeded timeout of {timeout_seconds:g} seconds",
            code=IssueCode.JOB_TIMEOUT,
            stage=stage,
            scope={"timeout_seconds": str(timeout_seconds)},
        )


class JobCancelledError(PipelineError):
    def __init__(self, *, stage: PipelineStage) -> None:
        super().__init__(
            "Job was cancelled",
            code=IssueCode.JOB_CANCELLED,
            stage=stage,
        )
