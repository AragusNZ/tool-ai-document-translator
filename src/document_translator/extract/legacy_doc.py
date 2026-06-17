"""Convert legacy .doc and .odt via pandoc."""
from __future__ import annotations

from pathlib import Path

from document_translator.lib.subprocess.libreoffice import convert_doc_to_docx
from document_translator.lib.subprocess.pandoc import run_pandoc_to_markdown


def extract_odt(path: Path, *, timeout_seconds: float | None = None) -> tuple[str, str]:
    return run_pandoc_to_markdown(path, timeout_seconds=timeout_seconds), "pandoc"


def extract_legacy_doc(path: Path, *, timeout_seconds: float | None = None) -> tuple[str, str]:
    try:
        return run_pandoc_to_markdown(path, timeout_seconds=timeout_seconds), "pandoc"
    except RuntimeError:
        from document_translator.extract.docx import extract_docx

        docx_path = convert_doc_to_docx(path, timeout_seconds=timeout_seconds)
        try:
            text, _warnings = extract_docx(docx_path)
            return text, "libreoffice+docx"
        finally:
            docx_path.unlink(missing_ok=True)
