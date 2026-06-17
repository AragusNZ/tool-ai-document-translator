from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from document_translator.config.formats import ExportFormat
from document_translator.export.pandoc import convert_markdown_with_pandoc


def test_convert_unsupported_format(tmp_path: Path) -> None:
    source = tmp_path / "doc.md"
    source.write_text("# Title", encoding="utf-8")
    target = tmp_path / "out.pdf"
    with pytest.raises(ValueError, match="does not support format"):
        convert_markdown_with_pandoc(source, target, ExportFormat.PDF)


def test_convert_missing_pandoc(tmp_path: Path) -> None:
    source = tmp_path / "doc.md"
    source.write_text("# Title", encoding="utf-8")
    target = tmp_path / "out.docx"
    with patch("document_translator.lib.subprocess.pandoc.shutil.which", return_value=None):
        with pytest.raises(RuntimeError, match="pandoc not found"):
            convert_markdown_with_pandoc(source, target, ExportFormat.DOCX)


def test_convert_pandoc_failure(tmp_path: Path) -> None:
    source = tmp_path / "doc.md"
    source.write_text("# Title\n\nBody.\n", encoding="utf-8")
    target = tmp_path / "out.docx"
    with patch("document_translator.lib.subprocess.pandoc.shutil.which", return_value="/usr/bin/pandoc"):
        with patch(
            "document_translator.lib.subprocess.pandoc.subprocess.run",
            return_value=subprocess.CompletedProcess([], 1, stderr="conversion failed"),
        ):
            with pytest.raises(RuntimeError, match="pandoc failed"):
                convert_markdown_with_pandoc(source, target, ExportFormat.DOCX)


@pytest.mark.parametrize("fmt", [ExportFormat.DOCX, ExportFormat.ODT, ExportFormat.RTF, ExportFormat.TXT])
def test_convert_success_mocked(tmp_path: Path, fmt: ExportFormat) -> None:
    source = tmp_path / "doc.md"
    source.write_text("# Title\n\nBody.\n", encoding="utf-8")
    target = tmp_path / f"out.{fmt.value}"

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        out_path = Path(cmd[cmd.index("-o") + 1])
        out_path.write_text("exported", encoding="utf-8")
        assert "-f" in cmd and "markdown+raw_tex" in cmd
        if fmt == ExportFormat.TXT:
            assert "-t" in cmd and "plain" in cmd
        return subprocess.CompletedProcess(cmd, 0)

    with patch("document_translator.lib.subprocess.pandoc.shutil.which", return_value="/usr/bin/pandoc"):
        with patch("document_translator.lib.subprocess.pandoc.subprocess.run", side_effect=fake_run):
            convert_markdown_with_pandoc(source, target, fmt)

    assert target.exists()
    assert target.read_text(encoding="utf-8") == "exported"
