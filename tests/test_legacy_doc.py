from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from document_translator.extract.legacy_doc import extract_legacy_doc, extract_odt
from document_translator.lib.subprocess.libreoffice import convert_doc_to_docx
from document_translator.lib.subprocess.pandoc import run_pandoc_to_markdown


def test_run_pandoc_missing_pandoc(tmp_path: Path) -> None:
    src = tmp_path / "file.odt"
    src.write_text("data", encoding="utf-8")
    with patch("document_translator.lib.subprocess.pandoc.shutil.which", return_value=None):
        with pytest.raises(RuntimeError, match="pandoc not found"):
            run_pandoc_to_markdown(src)


def test_run_pandoc_failure(tmp_path: Path) -> None:
    src = tmp_path / "file.odt"
    src.write_text("data", encoding="utf-8")
    with patch("document_translator.lib.subprocess.pandoc.shutil.which", return_value="/usr/bin/pandoc"):
        with patch(
            "document_translator.lib.subprocess.pandoc.subprocess.run",
            return_value=subprocess.CompletedProcess([], 1, stderr="conversion failed"),
        ):
            with pytest.raises(RuntimeError, match="pandoc conversion failed"):
                run_pandoc_to_markdown(src)


def test_run_pandoc_success(tmp_path: Path) -> None:
    src = tmp_path / "file.odt"
    src.write_text("data", encoding="utf-8")

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        out_path = Path(cmd[cmd.index("-o") + 1])
        out_path.write_text("Converted markdown body", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0)

    with patch("document_translator.lib.subprocess.pandoc.shutil.which", return_value="/usr/bin/pandoc"):
        with patch("document_translator.lib.subprocess.pandoc.subprocess.run", side_effect=fake_run):
            result = run_pandoc_to_markdown(src)

    assert result == "Converted markdown body\n"


def test_run_libreoffice_missing(tmp_path: Path) -> None:
    doc = tmp_path / "file.doc"
    doc.write_bytes(b"doc")
    with patch("document_translator.lib.subprocess.libreoffice.shutil.which", return_value=None):
        with pytest.raises(RuntimeError, match="libreoffice not found"):
            convert_doc_to_docx(doc)


def test_run_libreoffice_failure(tmp_path: Path) -> None:
    doc = tmp_path / "file.doc"
    doc.write_bytes(b"doc")
    with patch("document_translator.lib.subprocess.libreoffice.shutil.which", return_value="/usr/bin/libreoffice"):
        with patch(
            "document_translator.lib.subprocess.libreoffice.subprocess.run",
            return_value=subprocess.CompletedProcess([], 1, stderr="soffice failed"),
        ):
            with pytest.raises(RuntimeError, match="libreoffice conversion failed"):
                convert_doc_to_docx(doc)


def test_run_libreoffice_missing_output(tmp_path: Path) -> None:
    doc = tmp_path / "file.doc"
    doc.write_bytes(b"doc")

    with patch("document_translator.lib.subprocess.libreoffice.shutil.which", return_value="/usr/bin/libreoffice"):
        with patch(
            "document_translator.lib.subprocess.libreoffice.subprocess.run",
            return_value=subprocess.CompletedProcess([], 0),
        ):
            with pytest.raises(RuntimeError, match="did not produce expected output"):
                convert_doc_to_docx(doc)


def test_run_libreoffice_success(tmp_path: Path) -> None:
    doc = tmp_path / "sample.doc"
    doc.write_bytes(b"doc")

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        tmp_dir = Path(cmd[cmd.index("--outdir") + 1])
        converted = tmp_dir / f"{doc.stem}.docx"
        converted.write_bytes(b"docx-bytes")
        return subprocess.CompletedProcess(cmd, 0)

    with patch("document_translator.lib.subprocess.libreoffice.shutil.which", return_value="/usr/bin/libreoffice"):
        with patch("document_translator.lib.subprocess.libreoffice.subprocess.run", side_effect=fake_run):
            result_path = convert_doc_to_docx(doc)

    assert result_path.name == ".sample.converted.docx"
    assert result_path.exists()
    assert result_path.read_bytes() == b"docx-bytes"


def test_extract_odt_delegates_to_pandoc(tmp_path: Path) -> None:
    src = tmp_path / "file.odt"
    src.write_text("data", encoding="utf-8")
    with patch(
        "document_translator.extract.legacy_doc.run_pandoc_to_markdown",
        return_value="converted\n",
    ) as pandoc:
        text, method = extract_odt(src)
    pandoc.assert_called_once_with(src)
    assert text == "converted\n"
    assert method == "pandoc"


def test_extract_legacy_doc_pandoc_path(tmp_path: Path) -> None:
    src = tmp_path / "file.doc"
    src.write_bytes(b"doc")
    with patch(
        "document_translator.extract.legacy_doc.run_pandoc_to_markdown",
        return_value="via pandoc\n",
    ) as pandoc:
        text, method = extract_legacy_doc(src)
    pandoc.assert_called_once_with(src)
    assert text == "via pandoc\n"
    assert method == "pandoc"


def test_extract_legacy_doc_libreoffice_fallback(tmp_path: Path) -> None:
    src = tmp_path / "file.doc"
    src.write_bytes(b"doc")
    docx = tmp_path / ".file.converted.docx"
    docx.write_bytes(b"docx")

    with patch(
        "document_translator.extract.legacy_doc.run_pandoc_to_markdown",
        side_effect=RuntimeError("pandoc failed"),
    ):
        with patch(
            "document_translator.extract.legacy_doc.convert_doc_to_docx",
            return_value=docx,
        ):
            with patch(
                "document_translator.extract.docx.extract_docx",
                return_value=("from libreoffice\n", []),
            ):
                text, method = extract_legacy_doc(src)

    assert "from libreoffice" in text
    assert method == "libreoffice+docx"
    assert not docx.exists()
