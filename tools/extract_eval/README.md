# Extract evaluation (Phase 2 MVP)

Ad-hoc benchmark comparing PyMuPDF and LiteParse extraction backends. Not part of the installed package and not gated in CI.

## Usage

From the repository root:

```bash
# PyMuPDF only (default install)
python -m tools.extract_eval.benchmark --input tests/fixtures/sample.pdf

# Both backends on PDFs (requires optional extra for liteparse)
pip install -e '.[extract-liteparse]'
python -m tools.extract_eval.benchmark --input tests/fixtures/ --backends pymupdf liteparse

# Office/image inputs (liteparse only)
python -m tools.extract_eval.benchmark --input path/to/deck.pptx --backends liteparse

# JSON lines for scripting
python -m tools.extract_eval.benchmark --input path/to/docs/ --backends pymupdf liteparse --json
```

## Layout

| Path | Role |
|------|------|
| `providers/base.py` | `ExtractProvider` protocol and `BenchmarkRow` |
| `providers/pymupdf.py` | PyMuPDF backend adapter |
| `providers/liteparse.py` | LiteParse backend adapter |
| `benchmark.py` | CLI entry (`python -m tools.extract_eval.benchmark`) |

## Sample documents

Use any local corpus you have rights to use. **Do not** commit third-party PDFs or office files into this repo without verifying their license.

A local `other-projects/liteparse/` checkout may include demo documents for informal comparisons; those files are not redistributed with document-translator. Prefer your own fixtures or explicitly licensed corpora for committed golden tests (roadmap Phase 5).

See [THIRD_PARTY_NOTICES.md](../../THIRD_PARTY_NOTICES.md) for LiteParse licensing when redistributing images or bundles that include `[extract-liteparse]`.
