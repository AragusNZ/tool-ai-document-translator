from __future__ import annotations

import shutil
from enum import Enum
from importlib import import_module
from pathlib import Path

from pydantic import BaseModel

from document_translator.config.formats import ExportFormat
from document_translator.config.llms import LLMProvider, parse_llm_selector, provider_env_key
from document_translator.config.settings import PipelineConfig
from document_translator.lib.subprocess.tesseract import tesseract_available


class CheckStatus(str, Enum):
    OK = "ok"
    WARN = "warn"
    FAIL = "fail"


class PreflightCheck(BaseModel):
    name: str
    status: CheckStatus
    message: str
    required: bool = True


class PreflightResult(BaseModel):
    checks: list[PreflightCheck]

    @property
    def ready(self) -> bool:
        return all(check.status != CheckStatus.FAIL for check in self.checks if check.required)


def _provider_api_key(config: PipelineConfig, provider: LLMProvider) -> str | None:
    match provider:
        case LLMProvider.CURSOR:
            return config.cursor_api_key
        case LLMProvider.OPENAI:
            return config.openai_api_key
        case LLMProvider.ANTHROPIC:
            return config.anthropic_api_key
        case LLMProvider.GOOGLE:
            return config.google_api_key
    return None


def _provider_dependency_module(provider: LLMProvider) -> str | None:
    match provider:
        case LLMProvider.CURSOR:
            return "cursor_sdk"
        case LLMProvider.OPENAI:
            return "openai"
        case LLMProvider.ANTHROPIC:
            return "anthropic"
        case LLMProvider.GOOGLE:
            return "google.genai"
    return None


def _check_pandoc() -> PreflightCheck:
    if shutil.which("pandoc") is None:
        return PreflightCheck(
            name="pandoc",
            status=CheckStatus.FAIL,
            message="pandoc not found on PATH (install: sudo apt install pandoc)",
        )
    return PreflightCheck(
        name="pandoc",
        status=CheckStatus.OK,
        message="pandoc is available",
    )


def _check_weasyprint() -> PreflightCheck:
    try:
        import weasyprint  # noqa: F401
    except ImportError:
        return PreflightCheck(
            name="weasyprint",
            status=CheckStatus.FAIL,
            message="weasyprint Python package is not installed",
        )
    return PreflightCheck(
        name="weasyprint",
        status=CheckStatus.OK,
        message="weasyprint is importable",
    )


def _check_tesseract(*, required: bool) -> PreflightCheck:
    if tesseract_available():
        return PreflightCheck(
            name="tesseract",
            status=CheckStatus.OK,
            message="tesseract is available for PDF OCR",
            required=required,
        )
    return PreflightCheck(
        name="tesseract",
        status=CheckStatus.FAIL if required else CheckStatus.WARN,
        message="tesseract not available (scanned PDF OCR will be skipped)",
        required=required,
    )


def _check_libreoffice() -> PreflightCheck:
    if shutil.which("libreoffice") is None and shutil.which("soffice") is None:
        return PreflightCheck(
            name="libreoffice",
            status=CheckStatus.WARN,
            message="libreoffice not found on PATH (legacy .doc input/export may fail)",
            required=False,
        )
    return PreflightCheck(
        name="libreoffice",
        status=CheckStatus.OK,
        message="libreoffice is available",
        required=False,
    )


def _check_llm_provider_dependency(provider: LLMProvider) -> PreflightCheck:
    module_name = _provider_dependency_module(provider)
    if module_name is None:
        return PreflightCheck(
            name="llm_dependency",
            status=CheckStatus.FAIL,
            message=f"Unknown LLM provider: {provider.value}",
        )
    try:
        import_module(module_name)
    except ImportError:
        extra = provider.value
        return PreflightCheck(
            name="llm_dependency",
            status=CheckStatus.FAIL,
            message=(
                f"LLM provider {provider.value!r} requires optional dependency {module_name!r}; "
                f"install with pip install 'document-translator[{extra}]'"
            ),
        )
    return PreflightCheck(
        name="llm_dependency",
        status=CheckStatus.OK,
        message=f"LLM provider dependency {module_name} is installed",
    )


def _check_llm_api_key(config: PipelineConfig, provider: LLMProvider) -> PreflightCheck:
    env_key = provider_env_key(provider)
    api_key = _provider_api_key(config, provider)
    if not api_key:
        return PreflightCheck(
            name="llm_api_key",
            status=CheckStatus.FAIL,
            message=f"{env_key} is not set (required for {config.llm})",
        )
    return PreflightCheck(
        name="llm_api_key",
        status=CheckStatus.OK,
        message=f"{env_key} is set",
    )


def _check_runs_dir_writable(runs_dir: Path) -> PreflightCheck:
    try:
        runs_dir.mkdir(parents=True, exist_ok=True)
        probe = runs_dir / ".preflight-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        return PreflightCheck(
            name="runs_dir",
            status=CheckStatus.FAIL,
            message=f"runs directory is not writable: {runs_dir} ({exc})",
        )
    return PreflightCheck(
        name="runs_dir",
        status=CheckStatus.OK,
        message=f"runs directory is writable: {runs_dir}",
    )


def _export_needs_pandoc(export_format: ExportFormat | None) -> bool:
    if export_format is None:
        return True
    return export_format != ExportFormat.MD


def _export_needs_weasyprint(export_format: ExportFormat | None) -> bool:
    if export_format is None:
        return True
    return export_format == ExportFormat.PDF


def _export_needs_libreoffice(export_format: ExportFormat | None) -> bool:
    return export_format == ExportFormat.DOC


def run_preflight_checks(
    config: PipelineConfig,
    *,
    export_format: ExportFormat | None = None,
    require_ocr: bool = False,
) -> PreflightResult:
    checks: list[PreflightCheck] = []
    provider, _model = parse_llm_selector(config.llm)

    checks.append(_check_runs_dir_writable(config.resolve_runs_dir()))
    checks.append(_check_llm_provider_dependency(provider))
    checks.append(_check_llm_api_key(config, provider))

    if _export_needs_pandoc(export_format):
        checks.append(_check_pandoc())
    if _export_needs_weasyprint(export_format):
        checks.append(_check_weasyprint())
    if config.pdf_ocr or require_ocr:
        checks.append(_check_tesseract(required=require_ocr))
    if _export_needs_libreoffice(export_format):
        checks.append(_check_libreoffice())

    return PreflightResult(checks=checks)
