from __future__ import annotations

from pathlib import Path

import pytest

from document_translator.config.formats import ExportFormat, resolve_export_format


@pytest.mark.parametrize(
    ("suffix", "expected"),
    [
        (".pdf", ExportFormat.PDF),
        (".docx", ExportFormat.DOCX),
        (".doc", ExportFormat.DOC),
        (".odt", ExportFormat.ODT),
        (".rtf", ExportFormat.RTF),
        (".txt", ExportFormat.TXT),
        (".md", ExportFormat.MD),
        (".markdown", ExportFormat.MD),
    ],
)
def test_resolve_export_format_from_input_suffix(tmp_path: Path, suffix: str, expected: ExportFormat) -> None:
    path = tmp_path / f"file{suffix}"
    path.write_text("content", encoding="utf-8")
    assert resolve_export_format(input_path=path, requested=None) == expected


def test_resolve_export_format_unknown_suffix_defaults_to_pdf(tmp_path: Path) -> None:
    path = tmp_path / "file.xyz"
    path.write_text("content", encoding="utf-8")
    assert resolve_export_format(input_path=path, requested=None) == ExportFormat.PDF


def test_resolve_export_format_requested_overrides_input(tmp_path: Path) -> None:
    path = tmp_path / "file.txt"
    path.write_text("content", encoding="utf-8")
    assert resolve_export_format(input_path=path, requested=ExportFormat.PDF) == ExportFormat.PDF
