"""Extract text from PDF and normalize slide markers."""
from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from document_translator.config.defaults import (
    DEFAULT_EXTRACT_DPI,
    DEFAULT_PDF_OCR_LANGUAGES,
    PDF_OCR_MIN_CHARS_PER_PAGE,
)
from document_translator.extract.debug import log_extract_page
from document_translator.extract.ocr_http import (
    OcrHttpError,
    recognize_image,
    tesseract_lang_to_http,
)
from document_translator.lib.subprocess.tesseract import tesseract_available


def resolve_pdf_ocr_workers(configured: int | None) -> int:
    if configured is not None:
        return max(1, configured)
    cpu = os.cpu_count() or 2
    return max(1, min(4, cpu - 1))


def extract_with_pymupdf(
    pdf_path: Path,
    *,
    ocr_enabled: bool = True,
    ocr_languages: str = DEFAULT_PDF_OCR_LANGUAGES,
    ocr_min_chars_per_page: int = PDF_OCR_MIN_CHARS_PER_PAGE,
    ocr_server_url: str | None = None,
    ocr_workers: int | None = None,
    render_dpi: float = DEFAULT_EXTRACT_DPI,
    extract_debug: bool = False,
    source_file: str | None = None,
) -> tuple[str, int, str, tuple[str, ...], int, bool, tuple[dict[str, Any], ...]]:
    import fitz

    doc = fitz.open(pdf_path)
    try:
        native_by_index: dict[int, str] = {}
        sparse_indices: list[int] = []
        for page in doc:
            native = page.get_text()
            native_by_index[page.number] = native
            if ocr_enabled and len(native.strip()) < ocr_min_chars_per_page:
                sparse_indices.append(page.number)

        ocr_by_index: dict[int, str] = {}
        warnings: list[str] = []
        ocr_unavailable = False
        worker_count = resolve_pdf_ocr_workers(ocr_workers)

        if ocr_enabled and sparse_indices:
            if ocr_server_url:
                ocr_by_index, ocr_warnings = _ocr_pages_concurrent_http(
                    pdf_path,
                    sparse_indices,
                    server_url=ocr_server_url,
                    language=tesseract_lang_to_http(ocr_languages),
                    dpi=render_dpi,
                    workers=worker_count,
                )
                warnings.extend(ocr_warnings)
            elif tesseract_available():
                ocr_by_index, ocr_warnings = _ocr_pages_concurrent_tesseract(
                    pdf_path,
                    sparse_indices,
                    language=ocr_languages,
                    workers=worker_count,
                )
                warnings.extend(ocr_warnings)
            else:
                ocr_unavailable = True

        page_texts: list[str] = []
        page_stats: list[dict[str, Any]] = []
        ocr_pages = 0
        for page_index in sorted(native_by_index):
            native = native_by_index[page_index]
            text = native
            ocr_applied = False
            ocr_method = "native"
            ocr_text = ocr_by_index.get(page_index)
            if ocr_text is not None and len(ocr_text.strip()) > len(text.strip()):
                text = ocr_text
                ocr_applied = True
                ocr_pages += 1
                ocr_method = "http" if ocr_server_url else "tesseract"

            page_texts.append(text)
            page_stats.append(
                {
                    "page_num": page_index + 1,
                    "char_count": len(text.strip()),
                    "ocr": ocr_applied,
                    "text_item_count": None,
                    "method": ocr_method,
                }
            )
            if extract_debug:
                log_extract_page(
                    backend="pymupdf",
                    page_num=page_index + 1,
                    native_chars=len(native.strip()),
                    final_chars=len(text.strip()),
                    ocr_applied=ocr_applied,
                    ocr_method=ocr_method,
                    source_file=source_file,
                )

        page_count = doc.page_count
    finally:
        doc.close()

    method = "pymupdf+ocr" if ocr_pages > 0 else "pymupdf"
    return (
        "\n".join(page_texts),
        page_count,
        method,
        tuple(warnings),
        ocr_pages,
        ocr_unavailable,
        tuple(page_stats),
    )


def _render_page_png(page: Any, *, dpi: float) -> bytes:
    pixmap = page.get_pixmap(dpi=dpi)
    return pixmap.tobytes("png")


def _ocr_page_tesseract(pdf_path: Path, page_index: int, *, language: str) -> tuple[int, str]:
    import fitz

    doc = fitz.open(pdf_path)
    try:
        page = doc[page_index]
        return page_index, _ocr_page_text(page, language)
    finally:
        doc.close()


def _ocr_page_http(
    pdf_path: Path,
    page_index: int,
    *,
    server_url: str,
    language: str,
    dpi: float,
) -> tuple[int, str]:
    import fitz

    doc = fitz.open(pdf_path)
    try:
        page = doc[page_index]
        png_bytes = _render_page_png(page, dpi=dpi)
    finally:
        doc.close()
    text = recognize_image(server_url, png_bytes, language=language)
    return page_index, text


def _ocr_pages_concurrent_tesseract(
    pdf_path: Path,
    page_indices: list[int],
    *,
    language: str,
    workers: int,
) -> tuple[dict[int, str], list[str]]:
    results: dict[int, str] = {}
    warnings: list[str] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_ocr_page_tesseract, pdf_path, index, language=language): index
            for index in page_indices
        }
        for future in as_completed(futures):
            page_index = futures[future]
            try:
                idx, text = future.result()
                results[idx] = text
            except Exception as exc:
                warnings.append(f"OCR failed for page {page_index + 1}: {exc}")
    return results, warnings


def _ocr_pages_concurrent_http(
    pdf_path: Path,
    page_indices: list[int],
    *,
    server_url: str,
    language: str,
    dpi: float,
    workers: int,
) -> tuple[dict[int, str], list[str]]:
    results: dict[int, str] = {}
    warnings: list[str] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                _ocr_page_http,
                pdf_path,
                index,
                server_url=server_url,
                language=language,
                dpi=dpi,
            ): index
            for index in page_indices
        }
        for future in as_completed(futures):
            page_index = futures[future]
            try:
                idx, text = future.result()
                results[idx] = text
            except OcrHttpError as exc:
                warnings.append(f"HTTP OCR failed for page {page_index + 1}: {exc}")
            except Exception as exc:
                warnings.append(f"OCR failed for page {page_index + 1}: {exc}")
    return results, warnings


def _ocr_page_text(page: Any, language: str) -> str:
    textpage = page.get_textpage_ocr(language=language)
    return page.get_text(textpage=textpage)


def normalize_slides(text: str) -> str:
    lines = text.splitlines()
    out: list[str] = []
    for line in lines:
        m = re.match(r"^\s*--\s*(\d+)\s+of\s+\d+\s*--\s*$", line.strip())
        if m:
            out.append(f"--- Slide {int(m.group(1))} ---")
        else:
            out.append(line)
    return "\n".join(out).strip() + "\n"


def extract_pdf(
    path: Path,
    *,
    ocr_enabled: bool = True,
    ocr_languages: str = DEFAULT_PDF_OCR_LANGUAGES,
    ocr_min_chars_per_page: int = PDF_OCR_MIN_CHARS_PER_PAGE,
    ocr_server_url: str | None = None,
    ocr_workers: int | None = None,
    render_dpi: float = DEFAULT_EXTRACT_DPI,
    extract_debug: bool = False,
    source_file: str | None = None,
) -> tuple[str, int, str, tuple[str, ...], int, bool, tuple[dict[str, Any], ...]]:
    raw, page_count, method, warnings, ocr_pages, ocr_unavailable, page_stats = extract_with_pymupdf(
        path,
        ocr_enabled=ocr_enabled,
        ocr_languages=ocr_languages,
        ocr_min_chars_per_page=ocr_min_chars_per_page,
        ocr_server_url=ocr_server_url,
        ocr_workers=ocr_workers,
        render_dpi=render_dpi,
        extract_debug=extract_debug,
        source_file=source_file,
    )
    return (
        normalize_slides(raw),
        page_count,
        method,
        warnings,
        ocr_pages,
        ocr_unavailable,
        page_stats,
    )
