from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from document_translator.config.settings import PipelineConfig
from document_translator.extract.backends.liteparse import LiteParseBackend
from document_translator.extract.backends.routing import (
    LITEPARSE_SUFFIXES,
    get_backend,
    resolve_backend_name,
    uses_backend_routing,
)
from document_translator.extract.common import ExtractionResult, extract_single_file


@pytest.mark.parametrize(
    ("suffix", "expected"),
    [
        (".pdf", True),
        (".pptx", True),
        (".png", True),
        (".docx", False),
        (".txt", False),
    ],
)
def test_uses_backend_routing(suffix: str, expected: bool) -> None:
    assert uses_backend_routing(suffix) is expected


@pytest.mark.parametrize(
    ("suffix", "backend_setting", "expected"),
    [
        (".pdf", "auto", "pymupdf"),
        (".pdf", "pymupdf", "pymupdf"),
        (".pdf", "liteparse", "liteparse"),
        (".pptx", "auto", "liteparse"),
        (".pptx", "liteparse", "liteparse"),
    ],
)
def test_resolve_backend_name(suffix: str, backend_setting: str, expected: str) -> None:
    config = PipelineConfig(extract_backend=backend_setting)  # type: ignore[arg-type]
    assert resolve_backend_name(suffix, config) == expected


def test_resolve_backend_name_pymupdf_rejects_office_suffix() -> None:
    config = PipelineConfig(extract_backend="pymupdf")
    with pytest.raises(RuntimeError, match="PyMuPDF backend does not support"):
        resolve_backend_name(".pptx", config)


def test_get_backend_returns_named_instances() -> None:
    assert get_backend("pymupdf").name == "pymupdf"
    assert get_backend("liteparse").name == "liteparse"


def test_liteparse_backend_import_error() -> None:
    backend = LiteParseBackend()
    with patch.dict("sys.modules", {"liteparse": None}):
        with pytest.raises(RuntimeError, match="LiteParse is not installed"):
            backend.extract(Path("doc.pdf"), config=PipelineConfig())


def test_liteparse_backend_maps_parse_result(tmp_path: Path) -> None:
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    ocr_item = MagicMock(confidence=0.95)
    native_item = MagicMock(confidence=None)
    page = MagicMock()
    page.page_num = 1
    page.text = "LiteParse body"
    page.text_items = [native_item, ocr_item]
    parse_result = MagicMock()
    parse_result.text = "LiteParse body"
    parse_result.pages = [page]

    parser = MagicMock()
    parser.parse.return_value = parse_result

    liteparse_module = MagicMock()
    liteparse_module.LiteParse.return_value = parser

    backend = LiteParseBackend()
    with patch.dict("sys.modules", {"liteparse": liteparse_module}):
        result = backend.extract(pdf, config=PipelineConfig())

    assert result.text.strip() == "LiteParse body"
    assert result.pages == 1
    assert result.conversion_method == "liteparse"
    assert result.extract_backend == "liteparse"
    assert result.ocr_pages == 1
    assert result.layout_json is not None
    assert result.layout_json["pages"][0]["text_items"]
    assert result.extract_page_stats[0]["ocr"] is True
    parser.parse.assert_called_once_with(str(pdf))


def test_liteparse_backend_passes_ocr_server_url(tmp_path: Path) -> None:
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    page = MagicMock(page_num=1, text="body", text_items=[])
    parse_result = MagicMock(text="body", pages=[page])
    parser = MagicMock(parse=MagicMock(return_value=parse_result))
    liteparse_module = MagicMock(LiteParse=MagicMock(return_value=parser))
    config = PipelineConfig(pdf_ocr_server_url="http://localhost:8828/ocr")

    backend = LiteParseBackend()
    with patch.dict("sys.modules", {"liteparse": liteparse_module}):
        backend.extract(pdf, config=config)

    liteparse_module.LiteParse.assert_called_once_with(
        ocr_enabled=True,
        ocr_language="eng",
        ocr_server_url="http://localhost:8828/ocr",
    )


def test_liteparse_backend_passes_extract_options(tmp_path: Path) -> None:
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    page = MagicMock(page_num=1, text="body", text_items=[])
    parse_result = MagicMock(text="body", pages=[page])
    parser = MagicMock(parse=MagicMock(return_value=parse_result))
    liteparse_module = MagicMock(LiteParse=MagicMock(return_value=parser))
    config = PipelineConfig(
        target_pages="1-2",
        pdf_password="secret",
        extract_dpi=200.0,
    )

    backend = LiteParseBackend()
    with patch.dict("sys.modules", {"liteparse": liteparse_module}):
        backend.extract(pdf, config=config)

    liteparse_module.LiteParse.assert_called_once_with(
        ocr_enabled=True,
        ocr_language="eng",
        target_pages="1-2",
        password="secret",
        dpi=200.0,
    )


def test_liteparse_backend_captures_screenshots(tmp_path: Path) -> None:
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    page = MagicMock(page_num=1, text="body", text_items=[])
    parse_result = MagicMock(text="body", pages=[page])
    shot = MagicMock(page_num=1, image_bytes=b"png-bytes")
    parser = MagicMock(parse=MagicMock(return_value=parse_result), screenshot=MagicMock(return_value=[shot]))
    liteparse_module = MagicMock(LiteParse=MagicMock(return_value=parser))
    config = PipelineConfig(extract_screenshots=True)

    backend = LiteParseBackend()
    with patch.dict("sys.modules", {"liteparse": liteparse_module}):
        result = backend.extract(pdf, config=config)

    assert len(result.screenshot_paths) == 1
    assert result.screenshot_paths[0].read_bytes() == b"png-bytes"
    assert result.screenshot_temp_dir is not None


def test_extract_single_file_pdf_uses_pymupdf_backend_by_default(minimal_pdf: Path) -> None:
    with patch("document_translator.extract.backends.pymupdf.extract_pdf") as extract_pdf_mock:
        extract_pdf_mock.return_value = ("text\n", 1, "pymupdf", (), 0, False, ())
        result = extract_single_file(minimal_pdf)

    extract_pdf_mock.assert_called_once()
    assert result.conversion_method == "pymupdf"
    assert result.extract_backend == "pymupdf"


def test_extract_single_file_pdf_respects_no_ocr_config(minimal_pdf: Path) -> None:
    config = PipelineConfig(pdf_ocr=False)
    with patch("document_translator.extract.backends.pymupdf.extract_pdf") as extract_pdf_mock:
        extract_pdf_mock.return_value = ("text\n", 1, "pymupdf", (), 0, False, ())
        result = extract_single_file(minimal_pdf, config=config)

    extract_pdf_mock.assert_called_once_with(
        minimal_pdf,
        ocr_enabled=False,
        ocr_languages="eng",
        ocr_server_url=None,
        ocr_workers=None,
        render_dpi=150.0,
        extract_debug=False,
        source_file=minimal_pdf.name,
    )
    assert result.conversion_method == "pymupdf"


def test_extract_single_file_pdf_uses_configured_ocr_languages(minimal_pdf: Path) -> None:
    config = PipelineConfig(pdf_ocr_languages="eng+spa")
    with patch("document_translator.extract.backends.pymupdf.extract_pdf") as extract_pdf_mock:
        extract_pdf_mock.return_value = ("text\n", 1, "pymupdf", (), 0, False, ())
        extract_single_file(minimal_pdf, config=config)

    assert extract_pdf_mock.call_args.kwargs["ocr_languages"] == "eng+spa"


def test_extract_single_file_liteparse_backend(minimal_pdf: Path) -> None:
    config = PipelineConfig(extract_backend="liteparse")
    expected = ExtractionResult(
        text="from liteparse\n",
        pages=2,
        bytes=100,
        conversion_method="liteparse",
        extract_backend="liteparse",
    )
    with patch(
        "document_translator.extract.backends.liteparse.LiteParseBackend.extract",
        return_value=expected,
    ) as extract_mock:
        result = extract_single_file(minimal_pdf, config=config)

    extract_mock.assert_called_once()
    assert result.extract_backend == "liteparse"


def test_extract_single_file_liteparse_suffix_without_package(tmp_path: Path) -> None:
    office = tmp_path / "deck.pptx"
    office.write_bytes(b"PK")
    config = PipelineConfig(extract_backend="auto")

    with patch.dict("sys.modules", {"liteparse": None}):
        with pytest.raises(RuntimeError, match="LiteParse is not installed"):
            extract_single_file(office, config=config)


@pytest.mark.parametrize("suffix", sorted(LITEPARSE_SUFFIXES))
def test_liteparse_suffixes_resolve_to_liteparse(suffix: str) -> None:
    config = PipelineConfig(extract_backend="auto")
    assert resolve_backend_name(suffix, config) == "liteparse"
