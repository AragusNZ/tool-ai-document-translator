from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from document_translator.config.defaults import (
    LARGE_INPUT_BYTES,
    LOW_TEXT_DENSITY_CHARS_PER_PAGE,
    REPLACEMENT_CHAR,
)
from document_translator.config.formats import SUPPORTED_EXTENSIONS
from document_translator.config.settings import PipelineConfig
from document_translator.extract.docx import extract_docx
from document_translator.extract.legacy_doc import extract_legacy_doc, extract_odt
from document_translator.extract.backends.routing import get_backend, resolve_backend_name, uses_backend_routing
from document_translator.extract.rtf import strip_rtf
from document_translator.models import ExtractionAlert
from document_translator.storage.paths import JobPaths


@dataclass(frozen=True)
class ExtractionResult:
    text: str
    pages: int | None = None
    bytes: int = 0
    conversion_method: str | None = None
    conversion_warnings: tuple[str, ...] = field(default_factory=tuple)
    encoding_loss: bool = False
    ocr_pages: int = 0
    ocr_unavailable: bool = False
    extract_backend: str | None = None
    layout_text: str | None = None
    layout_json: dict[str, Any] | None = None
    screenshot_paths: tuple[Path, ...] = ()
    screenshot_temp_dir: Path | None = None
    extract_page_stats: tuple[dict[str, Any], ...] = ()


def liteparse_only_options_active(config: PipelineConfig) -> list[str]:
    options: list[str] = []
    if config.target_pages:
        options.append("target_pages")
    if config.pdf_password:
        options.append("pdf_password")
    if config.extract_dpi is not None:
        options.append("extract_dpi")
    if config.extract_screenshots:
        options.append("extract_screenshots")
    return options


def persist_extraction_sidecars(job_paths: JobPaths, extraction: ExtractionResult) -> None:
    if extraction.layout_json is not None:
        job_paths.extraction_layout_json.write_text(
            json.dumps(extraction.layout_json, indent=2) + "\n",
            encoding="utf-8",
        )

    if extraction.screenshot_paths:
        job_paths.screenshots_dir.mkdir(parents=True, exist_ok=True)
        for src in extraction.screenshot_paths:
            shutil.copy2(src, job_paths.screenshots_dir / src.name)

    if extraction.screenshot_temp_dir is not None and extraction.screenshot_temp_dir.exists():
        shutil.rmtree(extraction.screenshot_temp_dir, ignore_errors=True)


def normalize_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").strip() + "\n"


def _read_text_with_encoding_check(path: Path) -> tuple[str, bool]:
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    encoding_loss = REPLACEMENT_CHAR in text
    return normalize_text(text), encoding_loss


def extract_single_file(path: Path, *, config: PipelineConfig | None = None) -> ExtractionResult:
    file_bytes = path.stat().st_size
    suffix = path.suffix.lower()
    conversion_warnings: list[str] = []
    encoding_loss = False
    effective_config = config or PipelineConfig()

    if uses_backend_routing(suffix):
        backend_name = resolve_backend_name(suffix, effective_config)
        backend = get_backend(backend_name)
        return backend.extract(path, config=effective_config)

    if suffix in {".txt", ".md", ".markdown"}:
        text, encoding_loss = _read_text_with_encoding_check(path)
        return ExtractionResult(
            text=text,
            pages=None,
            bytes=file_bytes,
            conversion_method="direct",
            encoding_loss=encoding_loss,
        )
    if suffix == ".rtf":
        raw = path.read_text(encoding="utf-8", errors="ignore")
        plain, used_fallback = strip_rtf(raw)
        if used_fallback:
            conversion_warnings.append("striprtf unavailable; used regex RTF fallback")
        return ExtractionResult(
            text=normalize_text(plain),
            pages=None,
            bytes=file_bytes,
            conversion_method="striprtf" if not used_fallback else "rtf_regex_fallback",
            conversion_warnings=tuple(conversion_warnings),
        )
    if suffix == ".docx":
        text, warnings = extract_docx(path)
        return ExtractionResult(
            text=normalize_text(text),
            pages=None,
            bytes=file_bytes,
            conversion_method="mammoth",
            conversion_warnings=tuple(warnings),
        )
    if suffix == ".doc":
        timeout = None if config is None else config.subprocess_timeout_seconds
        text, method = extract_legacy_doc(path, timeout_seconds=timeout)
        return ExtractionResult(text=normalize_text(text), pages=None, bytes=file_bytes, conversion_method=method)
    if suffix == ".odt":
        timeout = None if config is None else config.subprocess_timeout_seconds
        text, method = extract_odt(path, timeout_seconds=timeout)
        return ExtractionResult(text=normalize_text(text), pages=None, bytes=file_bytes, conversion_method=method)

    raise RuntimeError(f"Unsupported file type: {path.suffix}")


def compute_extraction_alerts(result: ExtractionResult, file_name: str) -> list[ExtractionAlert]:
    alerts: list[ExtractionAlert] = []
    chars = len(result.text)
    pages = result.pages or 0

    if result.encoding_loss:
        alerts.append(
            ExtractionAlert(
                code="ENCODING_LOSS",
                message=f"{file_name}: invalid UTF-8 sequences replaced during read",
                scope={"file": file_name},
            )
        )
    if chars == 0:
        alerts.append(
            ExtractionAlert(
                code="EMPTY_EXTRACTION",
                message=f"{file_name}: extraction produced no text",
                scope={"file": file_name},
            )
        )
    if pages > 0:
        chars_per_page = chars / pages
        if chars_per_page < LOW_TEXT_DENSITY_CHARS_PER_PAGE:
            alerts.append(
                ExtractionAlert(
                    code="LOW_TEXT_DENSITY",
                    message=(
                        f"{file_name}: averaged {chars_per_page:.1f} chars/page — "
                        "possible scanned/image-only PDF"
                    ),
                    scope={"file": file_name},
                )
            )
    if file_bytes := result.bytes:
        if file_bytes > LARGE_INPUT_BYTES:
            alerts.append(
                ExtractionAlert(
                    code="LARGE_INPUT_FILE",
                    message=f"{file_name}: input file is {file_bytes:,} bytes",
                    scope={"file": file_name},
                )
            )
    return alerts


def build_extracted_markdown(
    result: ExtractionResult,
    *,
    source_file: str,
    alerts: list[ExtractionAlert],
) -> str:
    import json

    front_matter = {
        "source_file": source_file,
        "extracted_at": datetime.now(UTC).isoformat(),
        "page_count": result.pages,
        "conversion_method": result.conversion_method,
        "extraction_alerts": [a.model_dump() for a in alerts],
    }
    body = result.text.rstrip()
    return f"---\n{json.dumps(front_matter, indent=2)}\n---\n\n{body}\n"


def strip_front_matter(md: str) -> str:
    if md.startswith("---"):
        end = md.find("\n---", 3)
        if end != -1:
            return md[end + 4 :].lstrip("\n")
    return md


def supported_extension(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS
