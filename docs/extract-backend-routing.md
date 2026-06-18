# Extract backend routing (Phase 5)

Normative CLI behavior lives in [README.md](../../README.md). This document records **recommended** `--extract-backend` choices based on Phase 1–5 benchmarks and golden extraction fixtures.

## Summary

| Input | `auto` routing | Recommended backend | Notes |
|-------|----------------|---------------------|-------|
| `.pdf` | `pymupdf` | **`pymupdf`** (default) | Fast, no extra deps; Tesseract or HTTP OCR for sparse pages |
| `.pdf` (layout sidecars, screenshots, `target_pages`) | `pymupdf` | **`liteparse`** | Use when spatial artifacts or LiteParse-only flags are required |
| `.pptx`, `.ppt`, `.xlsx`, `.xls` | `liteparse` | **`liteparse`** | Requires `[extract-liteparse]` + LibreOffice on PATH |
| `.png`, `.jpg`, `.jpeg`, `.tiff`, `.webp` | `liteparse` | **`liteparse`** | Requires `[extract-liteparse]` + ImageMagick |
| `.docx`, `.txt`, `.rtf`, `.odt`, `.doc` | legacy extractors | *(unchanged)* | Not routed through `extract/backends/` |

**Do not** promote LiteParse as the default PDF backend in `auto` mode yet. Golden regression on `tests/fixtures/extract/` shows both backends produce stable text for simple PDFs, but PyMuPDF remains the lower-dependency default.

## Evidence

- **Golden suite:** `tests/fixtures/extract/` — 8 programmatic PDFs, SHA-256 hashes in `golden_manifest.json`
- **CI:** PyMuPDF golden runs on every PR (`tests/test_extract_regression.py`); LiteParse golden runs in [`.github/workflows/extract-liteparse.yml`](../../.github/workflows/extract-liteparse.yml)
- **Benchmark harness:** `python -m tools.extract_eval.benchmark --input tests/fixtures/extract --report report.html`

## When to override

```bash
# Default PDF path (no optional extras)
document-translator translate file.pdf

# LiteParse PDF with layout sidecars
document-translator translate file.pdf --extract-backend liteparse --extract-screenshots

# Office deck
document-translator translate deck.pptx   # auto → liteparse when installed
```

## Revisit triggers

Update this doc when:

- LiteParse golden pass rate diverges materially from PyMuPDF on expanded fixtures
- Layout-preserving translation (`--preserve-layout`, Phase 7) ships
- Benchmark HTML reports show consistent quality wins for LiteParse on specific PDF classes
