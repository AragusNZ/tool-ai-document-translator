from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from document_translator.config.formats import ExportFormat
from document_translator.export.converter import export_markdown
from document_translator.lib.subprocess.libreoffice import convert_docx_to_doc


def test_export_markdown_md_copies_file(tmp_path: Path) -> None:
    source = tmp_path / "doc.md"
    source.write_text("# Title\n\nBody.\n", encoding="utf-8")
    target = tmp_path / "out" / "final.md"
    export_markdown(source, target, ExportFormat.MD)
    assert target.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")


def test_export_markdown_pdf_delegates(tmp_path: Path) -> None:
    source = tmp_path / "doc.md"
    source.write_text("# Title", encoding="utf-8")
    target = tmp_path / "out.pdf"
    with patch("document_translator.export.converter.convert_markdown_to_pdf") as mock_pdf:
        export_markdown(source, target, ExportFormat.PDF)
    mock_pdf.assert_called_once_with(source, target, timeout_seconds=None)


@pytest.mark.parametrize("fmt", [ExportFormat.DOCX, ExportFormat.ODT, ExportFormat.RTF, ExportFormat.TXT])
def test_export_markdown_pandoc_formats(tmp_path: Path, fmt: ExportFormat) -> None:
    source = tmp_path / "doc.md"
    source.write_text("# Title", encoding="utf-8")
    target = tmp_path / f"out.{fmt.value}"
    with patch("document_translator.export.converter.convert_markdown_with_pandoc") as mock_pandoc:
        export_markdown(source, target, fmt)
    mock_pandoc.assert_called_once_with(source, target, fmt, timeout_seconds=None)


def test_export_markdown_doc_converts_via_docx(tmp_path: Path) -> None:
    source = tmp_path / "doc.md"
    source.write_text("# Title", encoding="utf-8")
    target = tmp_path / "out.doc"

    def fake_pandoc(src: Path, docx_path: Path, fmt: ExportFormat, **kwargs: object) -> None:
        assert fmt == ExportFormat.DOCX
        docx_path.write_bytes(b"docx-bytes")

    def fake_docx_to_doc(docx_path: Path, out: Path, **kwargs: object) -> None:
        assert docx_path.exists()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"doc-bytes")

    with patch("document_translator.export.converter.convert_markdown_with_pandoc", side_effect=fake_pandoc):
        with patch("document_translator.export.converter.convert_docx_to_doc", side_effect=fake_docx_to_doc):
            export_markdown(source, target, ExportFormat.DOC)

    assert target.read_bytes() == b"doc-bytes"


def test_export_markdown_doc_cleans_temp_docx(tmp_path: Path) -> None:
    source = tmp_path / "doc.md"
    source.write_text("# Title", encoding="utf-8")
    target = tmp_path / "out.doc"
    temp_paths: list[Path] = []

    def fake_pandoc(src: Path, docx_path: Path, fmt: ExportFormat, **kwargs: object) -> None:
        temp_paths.append(docx_path)
        docx_path.write_bytes(b"docx")

    with patch("document_translator.export.converter.convert_markdown_with_pandoc", side_effect=fake_pandoc):
        with patch("document_translator.export.converter.convert_docx_to_doc"):
            export_markdown(source, target, ExportFormat.DOC)

    assert temp_paths
    assert not temp_paths[0].exists()


def test_convert_docx_to_doc_missing_libreoffice(tmp_path: Path) -> None:
    docx = tmp_path / "file.docx"
    docx.write_bytes(b"docx")
    target = tmp_path / "file.doc"
    with patch("document_translator.lib.subprocess.libreoffice.shutil.which", return_value=None):
        with pytest.raises(RuntimeError, match="libreoffice not found"):
            convert_docx_to_doc(docx, target)


def test_convert_docx_to_doc_libreoffice_failure(tmp_path: Path) -> None:
    docx = tmp_path / "file.docx"
    docx.write_bytes(b"docx")
    target = tmp_path / "file.doc"
    with patch("document_translator.lib.subprocess.libreoffice.shutil.which", return_value="/usr/bin/libreoffice"):
        with patch(
            "document_translator.lib.subprocess.run.subprocess.run",
            return_value=subprocess.CompletedProcess([], 1, stderr="soffice failed"),
        ):
            with pytest.raises(RuntimeError, match="libreoffice conversion failed"):
                convert_docx_to_doc(docx, target)


def test_convert_docx_to_doc_missing_output(tmp_path: Path) -> None:
    docx = tmp_path / "file.docx"
    docx.write_bytes(b"docx")
    target = tmp_path / "file.doc"
    with patch("document_translator.lib.subprocess.libreoffice.shutil.which", return_value="/usr/bin/libreoffice"):
        with patch(
            "document_translator.lib.subprocess.run.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0),
        ):
            with pytest.raises(RuntimeError, match="did not produce expected output"):
                convert_docx_to_doc(docx, target)


def test_convert_docx_to_doc_success(tmp_path: Path) -> None:
    docx = tmp_path / "file.docx"
    docx.write_bytes(b"docx")
    target = tmp_path / "file.doc"

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        out_dir = Path(cmd[cmd.index("--outdir") + 1])
        (out_dir / "file.doc").write_bytes(b"legacy-doc")
        return subprocess.CompletedProcess(cmd, 0)

    with patch("document_translator.lib.subprocess.libreoffice.shutil.which", return_value="/usr/bin/libreoffice"):
        with patch("document_translator.lib.subprocess.run.subprocess.run", side_effect=fake_run):
            convert_docx_to_doc(docx, target)

    assert target.read_bytes() == b"legacy-doc"
