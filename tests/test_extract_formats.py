from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from document_translator.config.formats import LITEPARSE_INPUT_SUFFIXES, SUPPORTED_INPUT_SUFFIXES
from document_translator.extract.common import extract_single_file


def test_supported_input_suffixes_include_liteparse_formats() -> None:
    for suffix in LITEPARSE_INPUT_SUFFIXES:
        assert suffix in SUPPORTED_INPUT_SUFFIXES


def test_extract_liteparse_office_suffix_uses_backend(tmp_path: Path) -> None:
    deck = tmp_path / "deck.pptx"
    deck.write_bytes(b"PK")
    from document_translator.extract.common import ExtractionResult

    with patch(
        "document_translator.extract.backends.liteparse.LiteParseBackend.extract",
        return_value=ExtractionResult(
            text="slide text\n",
            pages=3,
            bytes=2,
            conversion_method="liteparse",
            extract_backend="liteparse",
        ),
    ) as extract_mock:
        result = extract_single_file(deck)

    extract_mock.assert_called_once()
    assert result.conversion_method == "liteparse"
    assert "slide text" in result.text


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


@pytest.fixture
def minimal_epub(tmp_path: Path) -> Path:
    import ebooklib
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_identifier("sample-epub-id")
    book.set_title("Sample EPUB")
    book.set_language("en")

    chapter = epub.EpubHtml(title="Chapter 1", file_name="chap_01.xhtml", lang="en")
    chapter.content = "<h1>Chapter</h1><p>Hello EPUB world.</p>"
    book.add_item(chapter)
    book.spine = ["nav", chapter]
    book.toc = [chapter]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    path = tmp_path / "sample.epub"
    epub.write_epub(str(path), book)
    return path


def test_extract_epub(minimal_epub: Path) -> None:
    result = extract_single_file(minimal_epub)
    assert "Hello EPUB world" in result.text
    assert result.conversion_method == "ebooklib"


def test_extract_html_with_markdownify_fallback(tmp_path: Path) -> None:
    html = tmp_path / "page.html"
    html.write_text("<html><body><h1>Title</h1><p>Hello HTML world.</p></body></html>", encoding="utf-8")

    with patch(
        "document_translator.extract.html.run_pandoc_to_markdown",
        side_effect=RuntimeError("pandoc unavailable"),
    ):
        result = extract_single_file(html)

    assert "Hello HTML world" in result.text
    assert result.conversion_method == "markdownify"
    assert result.conversion_warnings
