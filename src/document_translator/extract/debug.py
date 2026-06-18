from __future__ import annotations

from document_translator.observability.logging_setup import get_logger


def log_extract_page(
    *,
    backend: str,
    page_num: int,
    native_chars: int,
    final_chars: int,
    ocr_applied: bool,
    ocr_method: str,
    source_file: str | None = None,
) -> None:
    get_logger("document_translator.extract").debug(
        "extract page",
        extra={
            "extract_backend": backend,
            "page_num": page_num,
            "native_chars": native_chars,
            "final_chars": final_chars,
            "ocr_applied": ocr_applied,
            "ocr_method": ocr_method,
            "source_file": source_file,
        },
    )
