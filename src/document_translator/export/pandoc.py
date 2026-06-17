from __future__ import annotations

from pathlib import Path

from document_translator.config.formats import ExportFormat
from document_translator.lib.subprocess.pandoc import run_pandoc_convert

_PANDOC_FORMAT_ARGS: dict[ExportFormat, list[str]] = {
    ExportFormat.DOCX: [],
    ExportFormat.ODT: [],
    ExportFormat.RTF: [],
    ExportFormat.TXT: ["-t", "plain"],
}


def convert_markdown_with_pandoc(
    source: Path,
    target: Path,
    fmt: ExportFormat,
    *,
    timeout_seconds: float | None = None,
) -> None:
    if fmt not in _PANDOC_FORMAT_ARGS:
        raise ValueError(f"pandoc export does not support format: {fmt.value}")

    run_pandoc_convert(
        source,
        target,
        extra_args=_PANDOC_FORMAT_ARGS[fmt],
        timeout_seconds=timeout_seconds,
    )
