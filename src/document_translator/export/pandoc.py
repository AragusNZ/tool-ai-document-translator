from __future__ import annotations

from pathlib import Path

from document_translator.config.formats import ExportFormat
from document_translator.export.pdf import rtl_css_path
from document_translator.lib.subprocess.pandoc import run_pandoc_convert

_PANDOC_FORMAT_ARGS: dict[ExportFormat, list[str]] = {
    ExportFormat.DOCX: [],
    ExportFormat.ODT: [],
    ExportFormat.RTF: [],
    ExportFormat.TXT: ["-t", "plain"],
    ExportFormat.HTML: [],
    ExportFormat.EPUB: [],
}


def _pandoc_extra_args(
    fmt: ExportFormat,
    *,
    target_lang: str | None,
    rtl: bool,
) -> list[str]:
    extra = list(_PANDOC_FORMAT_ARGS[fmt])
    if target_lang:
        extra.append(f"--metadata=lang:{target_lang}")
    if rtl and fmt == ExportFormat.HTML:
        extra.extend(["--css", str(rtl_css_path()), "--standalone"])
    return extra


def convert_markdown_with_pandoc(
    source: Path,
    target: Path,
    fmt: ExportFormat,
    *,
    timeout_seconds: float | None = None,
    target_lang: str | None = None,
    rtl: bool = False,
) -> None:
    if fmt not in _PANDOC_FORMAT_ARGS:
        raise ValueError(f"pandoc export does not support format: {fmt.value}")

    run_pandoc_convert(
        source,
        target,
        extra_args=_pandoc_extra_args(fmt, target_lang=target_lang, rtl=rtl),
        timeout_seconds=timeout_seconds,
    )
