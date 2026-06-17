from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from document_translator.extract.common import (
    ExtractionResult,
    build_extracted_markdown,
    compute_extraction_alerts,
    extract_single_file,
    normalize_text,
    strip_front_matter,
    supported_extension,
)
from document_translator.extract.pdf import normalize_slides
from document_translator.extract.rtf import strip_rtf


def test_supported_extensions(tmp_path: Path) -> None:
    for ext in [".pdf", ".txt", ".docx", ".rtf", ".md"]:
        p = tmp_path / f"file{ext}"
        p.write_text("x", encoding="utf-8")
        assert supported_extension(p)


def test_extract_txt(tmp_path: Path) -> None:
    src = tmp_path / "sample.txt"
    src.write_text("Hello\n\nWorld", encoding="utf-8")
    result = extract_single_file(src)
    assert "Hello" in result.text
    assert result.conversion_method == "direct"


def test_extract_md_front_matter(tmp_path: Path) -> None:
    result = ExtractionResult(text="Body text", pages=None, bytes=10, conversion_method="direct")
    md = build_extracted_markdown(result, source_file="a.md", alerts=[])
    assert md.startswith("---")
    assert strip_front_matter(md).strip() == "Body text"


def test_extraction_alerts_empty() -> None:
    result = ExtractionResult(text="", pages=5, bytes=100)
    alerts = compute_extraction_alerts(result, "empty.pdf")
    codes = {a.code for a in alerts}
    assert "EMPTY_EXTRACTION" in codes


def test_normalize_slides() -> None:
    raw = "-- 1 of 10 --\nSlide content"
    out = normalize_slides(raw)
    assert "--- Slide 1 ---" in out


def test_strip_rtf_basic() -> None:
    rtf = r"{\rtf1\ansi Hello world}"
    text, _used_fallback = strip_rtf(rtf)
    assert "Hello" in text


def test_rtf_fallback_issues_issue(tmp_path: Path) -> None:
    from unittest.mock import patch

    from document_translator.errors import IssueCode
    from document_translator.config.settings import PipelineConfig
    from document_translator.models import TranslationOptions
    from document_translator.pipeline import DocumentTranslationService
    from document_translator.lib.llm import MockLLMClient

    rtf = tmp_path / "doc.rtf"
    rtf.write_text(r"{\rtf1\ansi Hola mundo contractual agreement}", encoding="utf-8")

    with patch(
        "document_translator.extract.common.strip_rtf",
        return_value=("Hola mundo contractual agreement", True),
    ):
        with patch("document_translator.pipeline.export_markdown"):
            config = PipelineConfig(runs_dir=tmp_path / "runs", root=tmp_path)
            service = DocumentTranslationService(config=config, llm=MockLLMClient(prefix="[EN] "))
            result = service.translate(rtf, TranslationOptions(job_id="rtf-fallback-job"))

    assert any(i.code == IssueCode.CONVERSION_DEGRADED for i in result.metadata.issues)


def test_normalize_text_crlf() -> None:
    assert normalize_text("Hello\r\nWorld\r") == "Hello\nWorld\n"


def test_extraction_alerts_low_text_density() -> None:
    result = ExtractionResult(text="short", pages=10, bytes=100)
    alerts = compute_extraction_alerts(result, "sparse.pdf")
    codes = {a.code for a in alerts}
    assert "LOW_TEXT_DENSITY" in codes


def test_extraction_alerts_large_input() -> None:
    result = ExtractionResult(text="content", pages=None, bytes=21_000_000)
    alerts = compute_extraction_alerts(result, "big.pdf")
    codes = {a.code for a in alerts}
    assert "LARGE_INPUT_FILE" in codes


def test_extraction_alerts_encoding_loss() -> None:
    result = ExtractionResult(text="hello\ufffdworld", pages=None, bytes=10, encoding_loss=True)
    alerts = compute_extraction_alerts(result, "bad.txt")
    codes = {a.code for a in alerts}
    assert "ENCODING_LOSS" in codes


def test_extract_txt_with_invalid_utf8(tmp_path: Path) -> None:
    src = tmp_path / "bad.txt"
    src.write_bytes(b"Hello \xff\xfe World")
    result = extract_single_file(src)
    assert result.encoding_loss is True


def test_strip_rtf_regex_fallback() -> None:
    import builtins

    real_import = builtins.__import__

    def fake_import(name: str, *args, **kwargs):  # noqa: ANN001
        if name.startswith("striprtf"):
            raise ImportError("no striprtf")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        text, used_fallback = strip_rtf(r"{\rtf1\ansi Hello fallback}")
    assert used_fallback is True
    assert "Hello fallback" in text


def test_extract_unsupported_suffix(tmp_path: Path) -> None:
    bad = tmp_path / "file.xyz"
    bad.write_text("data", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Unsupported"):
        extract_single_file(bad)
