# Extract evaluation

Ad-hoc benchmark comparing PyMuPDF and LiteParse extraction backends. Not part of the installed package.

## Usage

From the repository root:

```bash
# PyMuPDF only (default install)
python -m tools.extract_eval.benchmark --input tests/fixtures/extract

# Both backends on PDFs (requires optional extra for liteparse)
pip install -e '.[extract-liteparse]'
python -m tools.extract_eval.benchmark --input tests/fixtures/extract --backends pymupdf liteparse

# QA pass rate + HTML report (uses golden manifest when fixtures match)
python -m tools.extract_eval.benchmark \
  --input tests/fixtures/extract \
  --backends pymupdf \
  --qa \
  --report /tmp/extract-report.html

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
| `golden.py` | Shared golden manifest helpers (used by tests and benchmark QA) |
| `qa.py` | QA scoring (`min_chars`, golden hash checks) |
| `report.py` | HTML report generation |
| `benchmark.py` | CLI entry (`python -m tools.extract_eval.benchmark`) |

## Golden fixtures

Committed golden PDFs live in `tests/fixtures/extract/`. See that directory's README for regeneration and `UPDATE_GOLDEN=1` workflow. Backend routing recommendations: [docs/extract-backend-routing.md](../../docs/extract-backend-routing.md).

## Sample documents

Use any local corpus you have rights to use. **Do not** commit third-party PDFs or office files into this repo without verifying their license.

See [THIRD_PARTY_NOTICES.md](../../THIRD_PARTY_NOTICES.md) for LiteParse licensing when redistributing images or bundles that include `[extract-liteparse]`.
