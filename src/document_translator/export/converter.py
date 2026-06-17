from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from document_translator.config.formats import ExportFormat
from document_translator.export.pandoc import convert_markdown_with_pandoc
from document_translator.export.pdf import convert_markdown_to_pdf
from document_translator.lib.subprocess.libreoffice import convert_docx_to_doc


def export_markdown(
    source: Path,
    target: Path,
    fmt: ExportFormat,
    *,
    subprocess_timeout_seconds: float | None = None,
) -> None:
    if fmt == ExportFormat.PDF:
        convert_markdown_to_pdf(source, target, timeout_seconds=subprocess_timeout_seconds)
    elif fmt == ExportFormat.MD:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target, follow_symlinks=False)
    elif fmt == ExportFormat.DOC:
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
            docx_path = Path(tmp.name)
        try:
            convert_markdown_with_pandoc(
                source,
                docx_path,
                ExportFormat.DOCX,
                timeout_seconds=subprocess_timeout_seconds,
            )
            convert_docx_to_doc(docx_path, target, timeout_seconds=subprocess_timeout_seconds)
        finally:
            docx_path.unlink(missing_ok=True)
    elif fmt in (ExportFormat.DOCX, ExportFormat.ODT, ExportFormat.RTF, ExportFormat.TXT):
        convert_markdown_with_pandoc(
            source,
            target,
            fmt,
            timeout_seconds=subprocess_timeout_seconds,
        )
    else:
        raise ValueError(f"unsupported export format: {fmt.value}")
