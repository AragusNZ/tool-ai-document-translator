from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from document_translator.extract.common import extract_single_file


def test_extract_pdf(minimal_pdf: Path) -> None:
    result = extract_single_file(minimal_pdf)
    assert "Sample PDF text" in result.text
    assert result.pages == 1
    assert result.conversion_method == "pymupdf"


def test_extract_docx(minimal_docx: Path) -> None:
    result = extract_single_file(minimal_docx)
    assert "Hello DOCX world" in result.text
    assert result.conversion_method == "mammoth"


def test_extract_rtf_file(tmp_path: Path) -> None:
    rtf = tmp_path / "doc.rtf"
    rtf.write_text(r"{\rtf1\ansi Hello RTF world}", encoding="utf-8")
    result = extract_single_file(rtf)
    assert "Hello RTF world" in result.text
    assert result.conversion_method in {"striprtf", "rtf_regex_fallback"}


@pytest.mark.requires_pandoc
def test_extract_odt_with_pandoc(tmp_path: Path) -> None:
    if shutil.which("pandoc") is None:
        pytest.skip("pandoc not installed")

    odt = tmp_path / "sample.odt"
    # Minimal ODT is complex; use pandoc to create one from markdown.
    import subprocess

    md = tmp_path / "source.md"
    md.write_text("# Title\n\nODT extraction test.\n", encoding="utf-8")
    subprocess.run(
        ["pandoc", str(md), "-o", str(odt)],
        check=True,
        capture_output=True,
        text=True,
    )
    result = extract_single_file(odt)
    assert "ODT extraction test" in result.text
    assert result.conversion_method == "pandoc"


@pytest.mark.requires_pandoc
def test_extract_legacy_doc_via_pandoc(tmp_path: Path) -> None:
    doc = tmp_path / "sample.doc"
    doc.write_bytes(b"fake doc content")

    with patch(
        "document_translator.extract.legacy_doc.run_pandoc_to_markdown",
        return_value="Legacy doc extraction test content.\n",
    ):
        result = extract_single_file(doc)

    assert "Legacy doc extraction test" in result.text
    assert result.conversion_method == "pandoc"
