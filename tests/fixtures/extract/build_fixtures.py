#!/usr/bin/env python3
"""Generate committed extract golden PDF fixtures and manifest hashes."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from tools.extract_eval.golden import (  # noqa: E402
    FIXTURES_DIR,
    GoldenCase,
    normalized_text_hash,
    write_manifest_cases,
)


def _write_pdf(path: Path, pages: list[list[tuple[tuple[float, float], str]]]) -> None:
    import fitz

    doc = fitz.open()
    for placements in pages:
        page = doc.new_page()
        for (x, y), text in placements:
            page.insert_text((x, y), text)
    doc.save(path)
    doc.close()


def build_pdf_fixtures() -> dict[str, Path]:
    specs: dict[str, list[list[tuple[tuple[float, float], str]]]] = {
        "single_page_text.pdf": [
            [((72, 72), "Golden fixture: single page with plain text.")],
        ],
        "multi_page_three.pdf": [
            [((72, 72), "Golden page one content.")],
            [((72, 72), "Golden page two content.")],
            [((72, 72), "Golden page three content.")],
        ],
        "slide_markers.pdf": [
            [((72, 72), "-- 1 of 2 --"), ((72, 100), "Slide body one.")],
            [((72, 72), "-- 2 of 2 --"), ((72, 100), "Slide body two.")],
        ],
        "unicode_symbols.pdf": [
            [((72, 72), "Unicode: café, naïve, 日本語, emoji 🚀")],
        ],
        "empty_page_between.pdf": [
            [((72, 72), "Content before blank page.")],
            [],
            [((72, 72), "Content after blank page.")],
        ],
        "dual_column_text.pdf": [
            [
                ((72, 72), "Left column paragraph."),
                ((320, 72), "Right column paragraph."),
            ],
        ],
        "whitespace_edges.pdf": [
            [((72, 72), "  Padded text with spaces.  ")],
        ],
        "legal_keywords.pdf": [
            [
                (
                    (72, 72),
                    "WHEREAS the parties agree to this contract. "
                    "The Seller shall deliver goods. Liability is limited.",
                )
            ],
        ],
    }
    paths: dict[str, Path] = {}
    for name, pages in specs.items():
        path = FIXTURES_DIR / name
        _write_pdf(path, pages)
        paths[name] = path
    return paths


def _liteparse_available() -> bool:
    try:
        import liteparse  # noqa: F401
    except ImportError:
        return False
    return True


def build_manifest(paths: dict[str, Path]) -> list[GoldenCase]:
    from document_translator.config.settings import PipelineConfig
    from document_translator.extract.backends.liteparse import LiteParseBackend
    from document_translator.extract.backends.pymupdf import PyMuPDFBackend

    config = PipelineConfig(pdf_ocr=False)
    cases: list[GoldenCase] = []
    pymupdf = PyMuPDFBackend()

    for name, path in sorted(paths.items()):
        result = pymupdf.extract(path, config=config)
        cases.append(
            GoldenCase(
                file=name,
                backend="pymupdf",
                pdf_ocr=False,
                min_chars=10,
                normalized_text_sha256=normalized_text_hash(result.text),
            )
        )

    if _liteparse_available():
        liteparse = LiteParseBackend()
        for name, path in sorted(paths.items()):
            result = liteparse.extract(path, config=config)
            cases.append(
                GoldenCase(
                    file=name,
                    backend="liteparse",
                    pdf_ocr=False,
                    min_chars=10,
                    normalized_text_sha256=normalized_text_hash(result.text),
                    requires_liteparse=True,
                )
            )

    return cases


def main() -> int:
    paths = build_pdf_fixtures()
    cases = build_manifest(paths)
    write_manifest_cases(cases)
    print(f"Wrote {len(paths)} PDF fixtures and {len(cases)} golden cases to {FIXTURES_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
