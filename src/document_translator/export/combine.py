from __future__ import annotations

from pathlib import Path

from document_translator.config.formats import ExportFormat

_PLAIN_TEXT_FORMATS = frozenset({ExportFormat.TXT, ExportFormat.MD})


def build_export_markdown(
    cover_md: str,
    body_md: Path,
    fmt: ExportFormat,
    *,
    include_cover: bool = True,
) -> str:
    body = body_md.read_text(encoding="utf-8")
    if not include_cover:
        return body

    cover = cover_md.strip()

    if fmt in _PLAIN_TEXT_FORMATS:
        return f"{cover}\n\n---\n\n{body}"

    if fmt == ExportFormat.PDF:
        cover_block = f'<div class="cover-page">\n\n{cover}\n\n</div>'
        return f"{cover_block}\n\n{body}"

    # Pandoc-backed formats: \newpage requires markdown+raw_tex (see export/pandoc.py)
    return f"{cover}\n\n\\newpage\n\n{body}"
