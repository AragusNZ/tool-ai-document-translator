from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from document_translator.config.settings import PipelineConfig
from document_translator.extract.common import extract_single_file
from document_translator.extract.pdf import extract_pdf, extract_with_pymupdf
from document_translator.lib.subprocess.tesseract import require_tesseract, tesseract_available


def test_tesseract_available_when_binary_missing() -> None:
    with patch("document_translator.lib.subprocess.tesseract.shutil.which", return_value=None):
        assert tesseract_available() is False


def test_tesseract_available_when_binary_present() -> None:
    import pymupdf

    with patch("document_translator.lib.subprocess.tesseract.shutil.which", return_value="/usr/bin/tesseract"):
        with patch.object(pymupdf, "get_tessdata", return_value="/tessdata"):
            assert tesseract_available() is True


def test_require_tesseract_raises_when_unavailable() -> None:
    with patch("document_translator.lib.subprocess.tesseract.tesseract_available", return_value=False):
        with pytest.raises(RuntimeError, match="tesseract not found"):
            require_tesseract()


def _make_page(*, native_text: str, ocr_text: str) -> MagicMock:
    page = MagicMock()
    page.number = 0
    page.get_text.side_effect = lambda textpage=None: ocr_text if textpage is not None else native_text
    textpage = MagicMock()
    page.get_textpage_ocr.return_value = textpage
    return page


def test_extract_with_pymupdf_ocr_fallback_improves_sparse_page() -> None:
    page = _make_page(native_text="", ocr_text="Recovered OCR text for the scanned page.")
    doc = MagicMock()
    doc.__iter__.return_value = [page]
    doc.page_count = 1

    with patch("fitz.open", return_value=doc):
        with patch("document_translator.extract.pdf.tesseract_available", return_value=True):
            text, pages, method, warnings, ocr_pages, ocr_unavailable = extract_with_pymupdf(
                Path("scan.pdf"),
            )

    assert pages == 1
    assert "Recovered OCR text" in text
    assert method == "pymupdf+ocr"
    assert ocr_pages == 1
    assert ocr_unavailable is False
    assert warnings == ()


def test_extract_with_pymupdf_skips_ocr_when_disabled() -> None:
    page = _make_page(native_text="", ocr_text="Should not be used")
    doc = MagicMock()
    doc.__iter__.return_value = [page]
    doc.page_count = 1

    with patch("fitz.open", return_value=doc):
        text, _pages, method, warnings, ocr_pages, ocr_unavailable = extract_with_pymupdf(
            Path("scan.pdf"),
            ocr_enabled=False,
        )

    assert text == ""
    assert method == "pymupdf"
    assert ocr_pages == 0
    assert ocr_unavailable is False
    assert warnings == ()
    page.get_textpage_ocr.assert_not_called()


def test_extract_with_pymupdf_marks_tesseract_unavailable() -> None:
    page = _make_page(native_text="", ocr_text="unused")
    doc = MagicMock()
    doc.__iter__.return_value = [page]
    doc.page_count = 1

    with patch("fitz.open", return_value=doc):
        with patch("document_translator.extract.pdf.tesseract_available", return_value=False):
            _text, _pages, method, warnings, ocr_pages, ocr_unavailable = extract_with_pymupdf(
                Path("scan.pdf"),
            )

    assert method == "pymupdf"
    assert ocr_pages == 0
    assert ocr_unavailable is True
    assert warnings == ()


def test_extract_with_pymupdf_ocr_failure_adds_warning() -> None:
    page = _make_page(native_text="", ocr_text="unused")
    page.get_textpage_ocr.side_effect = RuntimeError("OCR engine failed")
    doc = MagicMock()
    doc.__iter__.return_value = [page]
    doc.page_count = 1

    with patch("fitz.open", return_value=doc):
        with patch("document_translator.extract.pdf.tesseract_available", return_value=True):
            _text, _pages, method, warnings, ocr_pages, ocr_unavailable = extract_with_pymupdf(
                Path("scan.pdf"),
            )

    assert method == "pymupdf"
    assert ocr_pages == 0
    assert ocr_unavailable is False
    assert warnings == ("OCR failed for page 1: OCR engine failed",)


def test_extract_with_pymupdf_hybrid_only_sparse_pages() -> None:
    native_page = _make_page(native_text="Native text layer content.", ocr_text="unused")
    native_page.number = 0
    sparse_page = _make_page(native_text="", ocr_text="OCR page two.")
    sparse_page.number = 1
    doc = MagicMock()
    doc.__iter__.return_value = [native_page, sparse_page]
    doc.page_count = 2

    with patch("fitz.open", return_value=doc):
        with patch("document_translator.extract.pdf.tesseract_available", return_value=True):
            text, pages, method, _warnings, ocr_pages, ocr_unavailable = extract_with_pymupdf(
                Path("mixed.pdf"),
            )

    assert pages == 2
    assert "Native text layer content." in text
    assert "OCR page two." in text
    assert method == "pymupdf+ocr"
    assert ocr_pages == 1
    assert ocr_unavailable is False
    native_page.get_textpage_ocr.assert_not_called()
    sparse_page.get_textpage_ocr.assert_called_once()


def test_extract_pdf_returns_normalized_text(minimal_pdf: Path) -> None:
    text, pages, method, warnings, ocr_pages, ocr_unavailable = extract_pdf(minimal_pdf)
    assert "Sample PDF text" in text
    assert pages == 1
    assert method == "pymupdf"
    assert warnings == ()
    assert ocr_pages == 0
    assert ocr_unavailable is False


def test_extract_single_file_pdf_respects_no_ocr_config(minimal_pdf: Path) -> None:
    config = PipelineConfig(pdf_ocr=False)
    with patch("document_translator.extract.backends.pymupdf.extract_pdf") as extract_pdf_mock:
        extract_pdf_mock.return_value = ("text\n", 1, "pymupdf", (), 0, False)
        result = extract_single_file(minimal_pdf, config=config)

    extract_pdf_mock.assert_called_once_with(
        minimal_pdf,
        ocr_enabled=False,
        ocr_languages="eng",
    )
    assert result.conversion_method == "pymupdf"


def test_extract_single_file_pdf_uses_configured_ocr_languages(minimal_pdf: Path) -> None:
    config = PipelineConfig(pdf_ocr_languages="eng+spa")
    with patch("document_translator.extract.backends.pymupdf.extract_pdf") as extract_pdf_mock:
        extract_pdf_mock.return_value = ("text\n", 1, "pymupdf", (), 0, False)
        extract_single_file(minimal_pdf, config=config)

    extract_pdf_mock.assert_called_once_with(
        minimal_pdf,
        ocr_enabled=True,
        ocr_languages="eng+spa",
    )


@pytest.mark.integration
def test_pipeline_emits_ocr_applied(minimal_pdf: Path, tmp_path: Path) -> None:
    from document_translator.errors import IssueCode
    from document_translator.extract.common import ExtractionResult
    from document_translator.lib.llm import MockLLMClient
    from document_translator.models import TranslationOptions
    from document_translator.pipeline import DocumentTranslationService

    config = PipelineConfig(runs_dir=tmp_path / "runs", root=tmp_path)
    service = DocumentTranslationService(config=config, llm=MockLLMClient(prefix="[EN] "))
    ocr_text = "Recovered scanned content. " * 20

    with patch(
        "document_translator.pipeline.extract_single_file",
        return_value=ExtractionResult(
            text=ocr_text,
            pages=1,
            bytes=100,
            conversion_method="pymupdf+ocr",
            ocr_pages=1,
        ),
    ):
        with patch("document_translator.pipeline.export_markdown"):
            result = service.translate(minimal_pdf, TranslationOptions(job_id="ocr-applied-job"))

    codes = {issue.code for issue in result.metadata.issues}
    assert IssueCode.OCR_APPLIED in codes


@pytest.mark.integration
def test_pipeline_emits_ocr_unavailable(minimal_pdf: Path, tmp_path: Path) -> None:
    from document_translator.errors import IssueCode
    from document_translator.extract.common import ExtractionResult
    from document_translator.lib.llm import MockLLMClient
    from document_translator.models import TranslationOptions
    from document_translator.pipeline import DocumentTranslationService

    config = PipelineConfig(runs_dir=tmp_path / "runs", root=tmp_path)
    service = DocumentTranslationService(config=config, llm=MockLLMClient(prefix="[EN] "))

    with patch(
        "document_translator.pipeline.extract_single_file",
        return_value=ExtractionResult(
            text="",
            pages=1,
            bytes=100,
            conversion_method="pymupdf",
            ocr_unavailable=True,
        ),
    ):
        with patch("document_translator.pipeline.export_markdown"):
            result = service.translate(minimal_pdf, TranslationOptions(job_id="ocr-unavailable-job"))

    codes = {issue.code for issue in result.metadata.issues}
    assert IssueCode.OCR_UNAVAILABLE in codes
    assert IssueCode.CONVERSION_DEGRADED not in codes


@pytest.mark.requires_tesseract
def test_extract_scanned_pdf_with_tesseract(scanned_pdf: Path) -> None:
    if not tesseract_available():
        pytest.skip("tesseract not installed")
    result = extract_single_file(scanned_pdf)
    assert result.pages == 1
    assert result.conversion_method in {"pymupdf", "pymupdf+ocr"}
