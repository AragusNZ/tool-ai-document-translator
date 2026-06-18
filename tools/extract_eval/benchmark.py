"""Compare extract backends on latency, character counts, and QA pass rate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Repo root on sys.path when run as `python -m tools.extract_eval.benchmark`
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from document_translator.config.formats import LITEPARSE_INPUT_SUFFIXES  # noqa: E402
from document_translator.config.settings import PipelineConfig  # noqa: E402
from tools.extract_eval.golden import golden_index, normalized_text_hash  # noqa: E402
from tools.extract_eval.providers.base import BenchmarkRow, ExtractProvider  # noqa: E402
from tools.extract_eval.providers.liteparse import LiteParseProvider  # noqa: E402
from tools.extract_eval.providers.pymupdf import PyMuPDFProvider  # noqa: E402
from tools.extract_eval.qa import score_benchmark_row, summarize_qa  # noqa: E402
from tools.extract_eval.report import render_html_report, write_html_report  # noqa: E402

_BENCHMARK_SUFFIXES = frozenset({".pdf"}) | LITEPARSE_INPUT_SUFFIXES
_PROVIDER_TYPES: dict[str, type[ExtractProvider]] = {
    "pymupdf": PyMuPDFProvider,
    "liteparse": LiteParseProvider,
}


def _collect_input_files(input_path: Path) -> list[Path]:
    if input_path.is_dir():
        files = [
            path
            for path in sorted(input_path.iterdir())
            if path.is_file() and path.suffix.lower() in _BENCHMARK_SUFFIXES
        ]
        return files
    if input_path.suffix.lower() in _BENCHMARK_SUFFIXES:
        return [input_path]
    return []


def _provider_for(name: str) -> ExtractProvider:
    provider_type = _PROVIDER_TYPES[name]
    return provider_type()


def run_benchmark(
    files: list[Path],
    *,
    backends: list[str],
    config: PipelineConfig,
) -> list[BenchmarkRow]:
    rows: list[BenchmarkRow] = []
    for path in files:
        suffix = path.suffix.lower()
        for backend_name in backends:
            if backend_name == "pymupdf" and suffix in LITEPARSE_INPUT_SUFFIXES:
                rows.append(
                    BenchmarkRow(
                        file=path.name,
                        backend=backend_name,
                        error=f"PyMuPDF backend does not support {suffix} files",
                    )
                )
                continue
            provider = _provider_for(backend_name)
            rows.append(provider.extract(path, config=config))
    return rows


def score_rows(
    rows: list[BenchmarkRow],
    *,
    files: list[Path],
    use_golden: bool,
) -> list:
    golden = golden_index() if use_golden else {}
    files_by_name = {path.name: path for path in files}
    qa_results = []
    for row in rows:
        case = golden.get((row.file, row.backend))
        min_chars = case.min_chars if case else 1
        expected_hash = case.normalized_text_sha256 if case else None
        actual_hash = None
        if case and not row.error:
            path = files_by_name.get(row.file)
            if path is not None:
                from tools.extract_eval.golden import extract_for_golden

                actual_hash = normalized_text_hash(extract_for_golden(case, path))
        qa_results.append(
            score_benchmark_row(
                row,
                min_chars=min_chars,
                expected_hash=expected_hash,
                actual_hash=actual_hash,
            )
        )
    return qa_results


def _print_rows(rows: list[BenchmarkRow], *, as_json: bool) -> None:
    if as_json:
        for row in rows:
            print(json.dumps(row.__dict__))
        return
    for row in rows:
        if row.error:
            print(f"{row.file}\t{row.backend}\tERROR\t{row.error}")
        else:
            print(
                f"{row.file}\t{row.backend}\t"
                f"{row.chars} chars\t{row.pages} pages\t{row.elapsed_ms} ms"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark extract backends on document inputs")
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Directory of supported files or a single input path",
    )
    parser.add_argument(
        "--backends",
        nargs="+",
        choices=sorted(_PROVIDER_TYPES),
        default=["pymupdf"],
        help="Backends to run (liteparse requires [extract-liteparse])",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON lines instead of a table")
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Write HTML QA report to this path",
    )
    parser.add_argument(
        "--qa",
        action="store_true",
        help="Print QA pass-rate summary (uses golden manifest when available)",
    )
    args = parser.parse_args(argv)

    files = _collect_input_files(args.input)
    if not files:
        print(
            f"No supported files found under {args.input} "
            f"(suffixes: {', '.join(sorted(_BENCHMARK_SUFFIXES))}).",
            file=sys.stderr,
        )
        return 1

    config = PipelineConfig(pdf_ocr=False)
    rows = run_benchmark(files, backends=args.backends, config=config)
    qa_results = score_rows(rows, files=files, use_golden=args.qa or args.report is not None)

    if args.qa:
        summary = summarize_qa(qa_results)
        print(
            f"QA pass rate: {summary['pass_rate']}% "
            f"({summary['passed']}/{summary['total']})"
        )

    if args.report is not None:
        html = render_html_report(rows=rows, qa_results=qa_results)
        write_html_report(args.report, html)
        print(f"Wrote HTML report to {args.report}")

    if not args.qa and args.report is None:
        _print_rows(rows, as_json=args.json)
    elif args.json:
        for row in rows:
            print(json.dumps(row.__dict__))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
