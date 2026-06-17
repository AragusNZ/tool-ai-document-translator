"""Convert legacy .doc and .odt via pandoc."""
from __future__ import annotations

from pathlib import Path

from document_translator.lib.subprocess.libreoffice import convert_doc_to_docx
from document_translator.lib.subprocess.pandoc import run_pandoc_to_markdown


def extract_odt(path: Path) -> tuple[str, str]:
    return run_pandoc_to_markdown(path), "pandoc"


def extract_legacy_doc(path: Path) -> tuple[str, str]:
    try:
        return run_pandoc_to_markdown(path), "pandoc"
    except RuntimeError:
        from document_translator.extract.docx import extract_docx

        docx_path = convert_doc_to_docx(path)
        try:
            text, _warnings = extract_docx(docx_path)
            return text, "libreoffice+docx"
        finally:
            docx_path.unlink(missing_ok=True)
