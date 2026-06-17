from __future__ import annotations

from pathlib import Path

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from document_translator.config.defaults import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_LANG_CONFIDENCE,
    DEFAULT_LLM_SELECTOR,
    DEFAULT_MAX_CONCURRENT_CHUNKS,
    DEFAULT_PDF_OCR_LANGUAGES,
    DEFAULT_SIMILARITY_THRESHOLD,
    DEFAULT_TRANSLATION_MODEL,
)
from document_translator.config.llms import (
    LLMProvider,
    format_llm_selector,
    resolve_llm_selector,
    validate_llm_selector,
)
from document_translator.project_root import get_project_root


class PipelineConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DOCUMENT_TRANSLATOR_",
        extra="ignore",
        populate_by_name=True,
    )

    root: Path = Field(default_factory=get_project_root)
    runs_dir: Path = Path("runs")
    llm: str = Field(
        default=DEFAULT_LLM_SELECTOR,
        validation_alias=AliasChoices("LLM", "DOCUMENT_TRANSLATOR_LLM"),
    )
    translation_model: str = Field(
        default=DEFAULT_TRANSLATION_MODEL,
        validation_alias=AliasChoices("TRANSLATION_MODEL", "DOCUMENT_TRANSLATOR_TRANSLATION_MODEL"),
    )
    cursor_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("CURSOR_API_KEY", "DOCUMENT_TRANSLATOR_CURSOR_API_KEY"),
    )
    openai_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_API_KEY", "DOCUMENT_TRANSLATOR_OPENAI_API_KEY"),
    )
    anthropic_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ANTHROPIC_API_KEY", "DOCUMENT_TRANSLATOR_ANTHROPIC_API_KEY"),
    )
    google_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GOOGLE_API_KEY", "DOCUMENT_TRANSLATOR_GOOGLE_API_KEY"),
    )
    chunk_size: int = DEFAULT_CHUNK_SIZE
    chunk_overlap_sentences: int = DEFAULT_CHUNK_OVERLAP
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD
    max_concurrent_chunks: int = DEFAULT_MAX_CONCURRENT_CHUNKS
    lang_confidence_threshold: float = DEFAULT_LANG_CONFIDENCE
    fail_on_empty_extraction: bool = False
    pdf_ocr: bool = True
    pdf_ocr_languages: str = DEFAULT_PDF_OCR_LANGUAGES
    keep_work_files: bool = False
    job_timeout_seconds: float | None = Field(
        default=None,
        validation_alias=AliasChoices("JOB_TIMEOUT", "DOCUMENT_TRANSLATOR_JOB_TIMEOUT"),
    )
    webhook_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("WEBHOOK_URL", "DOCUMENT_TRANSLATOR_WEBHOOK_URL"),
    )
    webhook_secret: str | None = Field(
        default=None,
        validation_alias=AliasChoices("WEBHOOK_SECRET", "DOCUMENT_TRANSLATOR_WEBHOOK_SECRET"),
    )
    webhook_timeout_seconds: float = 30.0
    log_level: str = "INFO"
    log_format: str = "text"
    sentry_dsn: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SENTRY_DSN", "DOCUMENT_TRANSLATOR_SENTRY_DSN"),
    )
    sentry_environment: str | None = None
    sentry_traces_sample_rate: float = 0.0
    sentry_report_severities: str | list[str] = "error"

    @field_validator("llm", mode="before")
    @classmethod
    def _normalize_llm(cls, value: object) -> str:
        if value is None:
            return DEFAULT_LLM_SELECTOR
        resolved = resolve_llm_selector(str(value))
        return validate_llm_selector(resolved)

    @model_validator(mode="after")
    def _apply_translation_model_compat(self) -> PipelineConfig:
        if self.llm == DEFAULT_LLM_SELECTOR and self.translation_model != DEFAULT_TRANSLATION_MODEL:
            object.__setattr__(
                self,
                "llm",
                format_llm_selector(LLMProvider.CURSOR, self.translation_model),
            )
        return self

    @field_validator("job_timeout_seconds", mode="before")
    @classmethod
    def _normalize_job_timeout(cls, value: object) -> float | None:
        if value is None or value == "":
            return None
        timeout = float(value)
        if timeout <= 0:
            raise ValueError("job_timeout_seconds must be positive")
        return timeout

    @field_validator("webhook_url", mode="before")
    @classmethod
    def _normalize_webhook_url(cls, value: object) -> str | None:
        if value is None or value == "":
            return None
        url = str(value).strip()
        if not url.startswith(("http://", "https://")):
            raise ValueError("webhook_url must start with http:// or https://")
        return url

    @field_validator("webhook_timeout_seconds", mode="before")
    @classmethod
    def _normalize_webhook_timeout(cls, value: object) -> float:
        if value is None or value == "":
            return 30.0
        timeout = float(value)
        if timeout <= 0:
            raise ValueError("webhook_timeout_seconds must be positive")
        return timeout

    @field_validator("sentry_report_severities", mode="before")
    @classmethod
    def _normalize_sentry_report_severities(cls, value: object) -> str | list[str]:
        if value is None:
            return "error"
        if isinstance(value, list):
            return value
        return str(value)

    def resolve_runs_dir(self) -> Path:
        runs = self.runs_dir
        if not runs.is_absolute():
            runs = self.root / runs
        return runs
