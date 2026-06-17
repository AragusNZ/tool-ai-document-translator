from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from tools.extract_eval.benchmark import _collect_input_files, run_benchmark
from tools.extract_eval.providers.base import BenchmarkRow


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
