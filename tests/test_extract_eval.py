from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from tools.extract_eval.benchmark import _collect_input_files, main, run_benchmark, score_rows
from tools.extract_eval.providers.base import BenchmarkRow
from tools.extract_eval.qa import QACheck, score_benchmark_row, summarize_qa
from tools.extract_eval.report import render_html_report, write_html_report


def test_collect_input_files_from_directory(tmp_path: Path) -> None:
    (tmp_path / "a.pdf").write_bytes(b"%PDF")
    (tmp_path / "b.txt").write_text("skip", encoding="utf-8")
    (tmp_path / "deck.pptx").write_bytes(b"PK")

    files = _collect_input_files(tmp_path)
    names = {path.name for path in files}
    assert names == {"a.pdf", "deck.pptx"}


def test_run_benchmark_skips_pymupdf_for_office_suffix(tmp_path: Path) -> None:
    deck = tmp_path / "deck.pptx"
    deck.write_bytes(b"PK")

    with patch(
        "tools.extract_eval.benchmark._provider_for",
        side_effect=AssertionError("provider should not be called"),
    ):
        rows = run_benchmark([deck], backends=["pymupdf"], config=object())  # type: ignore[arg-type]

    assert len(rows) == 1
    assert rows[0].error is not None
    assert "PyMuPDF backend does not support" in rows[0].error


def test_run_benchmark_uses_provider(tmp_path: Path) -> None:
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF")

    class FakeProvider:
        name = "pymupdf"

        def extract(self, path: Path, *, config: object) -> BenchmarkRow:
            return BenchmarkRow(
                file=path.name,
                backend=self.name,
                chars=10,
                pages=1,
                elapsed_ms=1.0,
                conversion_method="pymupdf",
            )

    with patch("tools.extract_eval.benchmark._provider_for", return_value=FakeProvider()):
        rows = run_benchmark([pdf], backends=["pymupdf"], config=object())  # type: ignore[arg-type]

    assert rows[0].chars == 10


def test_score_benchmark_row_passes_when_ok() -> None:
    row = BenchmarkRow(file="a.pdf", backend="pymupdf", chars=50, pages=1, elapsed_ms=1.0)
    result = score_benchmark_row(row, min_chars=10, expected_hash="abc", actual_hash="abc")
    assert result.passed
    assert not result.failures


def test_score_benchmark_row_fails_on_error() -> None:
    row = BenchmarkRow(file="a.pdf", backend="pymupdf", error="boom")
    result = score_benchmark_row(row, min_chars=1)
    assert not result.passed
    assert "extract_ok" in result.failures[0]


def test_score_benchmark_row_fails_on_hash_mismatch() -> None:
    row = BenchmarkRow(file="a.pdf", backend="pymupdf", chars=50, pages=1, elapsed_ms=1.0)
    result = score_benchmark_row(row, min_chars=1, expected_hash="aaa", actual_hash="bbb")
    assert not result.passed
    assert any("golden_hash" in failure for failure in result.failures)


def test_summarize_qa() -> None:
    from tools.extract_eval.qa import QAResult

    results = [
        QAResult(file="a.pdf", backend="pymupdf", checks=[QACheck("extract_ok", True)]),
        QAResult(file="b.pdf", backend="pymupdf", checks=[QACheck("extract_ok", False, "err")]),
    ]
    summary = summarize_qa(results)
    assert summary["total"] == 2
    assert summary["passed"] == 1
    assert summary["pass_rate"] == 50.0


def test_render_html_report_includes_summary() -> None:
    from tools.extract_eval.qa import QAResult

    rows = [BenchmarkRow(file="a.pdf", backend="pymupdf", chars=10, pages=1, elapsed_ms=1.0)]
    qa = [QAResult(file="a.pdf", backend="pymupdf", checks=[QACheck("extract_ok", True)])]
    html = render_html_report(rows=rows, qa_results=qa, title="Test report")
    assert "Test report" in html
    assert "100.0%" in html
    assert "a.pdf" in html


def test_write_html_report(tmp_path: Path) -> None:
    path = tmp_path / "subdir" / "report.html"
    write_html_report(path, "<html><body>ok</body></html>")
    assert path.read_text(encoding="utf-8") == "<html><body>ok</body></html>"


def test_benchmark_main_qa_and_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fixtures = Path(__file__).resolve().parent / "fixtures" / "extract"
    report_path = tmp_path / "report.html"

    exit_code = main(
        [
            "--input",
            str(fixtures),
            "--backends",
            "pymupdf",
            "--qa",
            "--report",
            str(report_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "QA pass rate:" in captured.out
    assert report_path.exists()
    assert "Extract evaluation report" in report_path.read_text(encoding="utf-8")


def test_score_rows_without_golden(tmp_path: Path) -> None:
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF")
    rows = [BenchmarkRow(file="sample.pdf", backend="pymupdf", chars=5, pages=1, elapsed_ms=1.0)]
    results = score_rows(rows, files=[pdf], use_golden=False)
    assert len(results) == 1
    assert results[0].passed
