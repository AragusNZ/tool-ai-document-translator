"""Extract text from PDF and normalize slide markers."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from document_translator.config.defaults import DEFAULT_PDF_OCR_LANGUAGES, PDF_OCR_MIN_CHARS_PER_PAGE
from document_translator.lib.subprocess.tesseract import tesseract_available


def extract_with_pymupdf(
    pdf_path: Path,
    *,
    ocr_enabled: bool = True,
    ocr_languages: str = DEFAULT_PDF_OCR_LANGUAGES,
    ocr_min_chars_per_page: int = PDF_OCR_MIN_CHARS_PER_PAGE,
) -> tuple[str, int, str, tuple[str, ...], int, bool]:
    import fitz

    doc = fitz.open(pdf_path)
    try:
        page_texts: list[str] = []
        warnings: list[str] = []
        ocr_pages = 0
        ocr_unavailable = False
        tesseract_checked = False
        tesseract_ok = False

        for page in doc:
            text = page.get_text()
            if ocr_enabled and len(text.strip()) < ocr_min_chars_per_page:
                if not tesseract_checked:
                    tesseract_ok = tesseract_available()
                    tesseract_checked = True
                if tesseract_ok:
                    try:
                        ocr_text = _ocr_page_text(page, ocr_languages)
                    except Exception as exc:
                        warnings.append(f"OCR failed for page {page.number + 1}: {exc}")
                    else:
                        if len(ocr_text.strip()) > len(text.strip()):
                            text = ocr_text
                            ocr_pages += 1
                else:
                    ocr_unavailable = True
            page_texts.append(text)

        page_count = doc.page_count
    finally:
        doc.close()

    method = "pymupdf+ocr" if ocr_pages > 0 else "pymupdf"
    return "\n".join(page_texts), page_count, method, tuple(warnings), ocr_pages, ocr_unavailable


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
) -> tuple[str, int, str, tuple[str, ...], int, bool]:
    raw, page_count, method, warnings, ocr_pages, ocr_unavailable = extract_with_pymupdf(
        path,
        ocr_enabled=ocr_enabled,
        ocr_languages=ocr_languages,
        ocr_min_chars_per_page=ocr_min_chars_per_page,
    )
    return normalize_slides(raw), page_count, method, warnings, ocr_pages, ocr_unavailable
