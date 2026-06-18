from __future__ import annotations

from pathlib import Path

from document_translator.config.defaults import DEFAULT_EXTRACT_DPI
from document_translator.config.settings import PipelineConfig
from document_translator.extract.pdf import extract_pdf


class PyMuPDFBackend:
    name = "pymupdf"

    def extract(self, path: Path, *, config: PipelineConfig):
        from document_translator.extract.common import ExtractionResult, normalize_text

        render_dpi = config.extract_dpi if config.extract_dpi is not None else DEFAULT_EXTRACT_DPI
        (
            text,
            pages,
            method,
            warnings,
            ocr_pages,
            ocr_unavailable,
            page_stats,
        ) = extract_pdf(
            path,
            ocr_enabled=config.pdf_ocr,
            ocr_languages=config.pdf_ocr_languages,
            ocr_server_url=config.pdf_ocr_server_url,
            ocr_workers=config.pdf_ocr_workers,
            render_dpi=render_dpi,
            extract_debug=config.extract_debug,
            source_file=path.name,
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
            extract_page_stats=page_stats,
        )
