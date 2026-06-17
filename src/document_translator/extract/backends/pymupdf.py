from __future__ import annotations

from pathlib import Path

from document_translator.config.settings import PipelineConfig
from document_translator.extract.pdf import extract_pdf


class PyMuPDFBackend:
    name = "pymupdf"

    def extract(self, path: Path, *, config: PipelineConfig):
        from document_translator.extract.common import ExtractionResult, normalize_text

        text, pages, method, warnings, ocr_pages, ocr_unavailable = extract_pdf(
            path,
            ocr_enabled=config.pdf_ocr,
            ocr_languages=config.pdf_ocr_languages,
        )
        file_bytes = path.stat().st_size
        return ExtractionResult(
            text=normalize_text(text),
            pages=pages,
            bytes=file_bytes,
            conversion_method=method,
            conversion_warnings=warnings,
            ocr_pages=ocr_pages,
            ocr_unavailable=ocr_unavailable,
            extract_backend=self.name,
        )
