# Roadmap

Planned improvements beyond the current `0.4.0` release. Not committed to a timeline.

Several extraction, OCR, and quality items below were informed by a review of [LiteParse](other-projects/liteparse/) (local-first spatial PDF parser with pluggable OCR, multi-format conversion, and evaluation harness). Document Translator stays **translation-first**; LiteParse is adopted as an **optional extraction backend**, not as a core dependency or full rewrite.

## Extraction strategy

**Principle:** Use LiteParse for hard parsing problems; own translation, export, and job orchestration. Do not reimplement LiteParse's Rust engine (spatial PDF parsing, grid projection, selective OCR merge) in Python.

```
Input file → extract/common.py (routing + ExtractionResult)
                 │
     ┌───────────┼───────────┬──────────────┐
     ▼           ▼           ▼              ▼
 direct read   Mammoth/     pymupdf        liteparse
 (.txt/.md)    Pandoc/RTF   (default PDF)  (optional: layout,
 (.docx etc.)               simple PDFs)    PPTX/XLSX/images,
                                            OCR, screenshots)
                 │
                 ▼
     markdown + translation pipeline (owned here)
```

| Concern | Approach |
|---------|----------|
| **Default PDF extraction** | Keep PyMuPDF (`extract/pdf.py`) — fewer native deps, already shipped |
| **Layout / multi-column PDFs, scanned quality** | Optional LiteParse backend (`--extract-backend liteparse`) |
| **PPTX / XLSX / images** | Route through LiteParse (convert-to-PDF + spatial extract); do not duplicate `conversion.rs` |
| **Simple DOCX, TXT, RTF, ODT** | Keep existing per-format extractors (Mammoth, direct read, etc.) — lighter than LibreOffice → PDF |
| **EPUB / HTML** | Build new extractors (LiteParse does not cover these) |
| **HTTP OCR** | Thin Python client on PyMuPDF path **or** LiteParse's built-in HTTP OCR when on that backend |
| **Translation, reconciliation, export** | Always owned in-house — LiteParse has no markdown output or job model |

**Packaging:** `pip install document-translator[extract-liteparse]` as an optional extra (Rust extension + PDFium). PyMuPDF remains the default install. Promote LiteParse to default for specific formats only if benchmarks on real corpora justify the heavier dependency.

**Adapter contract:** Map LiteParse `ParseResult` → existing `ExtractionResult` in `extract/common.py`; optional sidecar `01-extraction-layout.json` for `text_items` / bboxes. Pipeline (`pipeline.py`) stays backend-agnostic.

### Phase 1 — Pluggable backend (foundation)

- **Extract backend interface** — `extract/backends/` with `pymupdf` (default) and `liteparse` (optional) behind `extract_single_file()`; CLI `--extract-backend pymupdf|liteparse` and config JSON field.
- **LiteParse adapter** — `pip install document-translator[extract-liteparse]`; map `ParseResult.text` into `ExtractionResult`; write `01-extraction-layout.json` when spatial data is available.
- **Auto-routing** — Default `pymupdf` for `.pdf`; auto-select `liteparse` for PPTX/XLSX/images when the extra is installed (override via `--extract-backend`).
- **Cross-extractor benchmarks** — Compare pymupdf vs liteparse on ~10–20 representative docs (scanned PDFs, multi-column reports, slide decks) to justify defaults before wider rollout.

### Phase 2 — Extraction quality (delegate to LiteParse where hard)

- **Layout-preserving extract text** — Use LiteParse `text` output (reading-order, multi-column) as a separate field alongside simplified markdown body.
- **Extraction sidecar with bounding boxes** — `01-extraction-layout.json` from LiteParse `text_items`; surface spans in `metadata.json` for legal docs and thorough-mode reconciliation.
- **Partial document extraction** — `--target-pages` (e.g. `1-5,10`); delegate to active backend; prerequisite for checkpoint resume.
- **Encrypted PDF support** — `--pdf-password`; delegate to LiteParse on that backend.
- **Optional page screenshots** — `runs/{job_id}/screenshots/page-{n}.png` via LiteParse screenshot API.
- **Richer OCR triggers** — On PyMuPDF path: improve sparse-page heuristic only. On LiteParse path: use its selective OCR (corrupt cmap, vector gaps) — **do not port `ocr_merge.rs` to Python**.

### Phase 3 — Thin wrappers we still build

- **HTTP OCR client (PyMuPDF path)** — Small client per [LiteParse OCR API spec](other-projects/liteparse/OCR_API_SPEC.md); `--pdf-ocr-server-url` / env `DOCUMENT_TRANSLATOR_PDF_OCR_SERVER_URL`. On LiteParse path, prefer its native HTTP OCR integration.
- **Concurrent page OCR (PyMuPDF path only)** — Thread pool for sparse pages in large scanned PDFs. LiteParse path already supports `num_workers`.
- **Extraction debug mode** — Env `DOCUMENT_TRANSLATOR_EXTRACT_DEBUG=1` (or CLI flag): per-page method, char count, OCR trigger reason, backend name.
- **Extract-stage metrics in `metadata.json`** — Per-page `extraction_method`, `ocr_applied`, `native_char_count`, `ocr_char_count`, `extract_duration_ms`, `extract_backend`.
- **Sentry breadcrumbs for extract** — Page count, OCR pages, backend, conversion tool.

## Input formats

- **PPTX / XLSX / images** — Via LiteParse backend (LibreOffice/ImageMagick → PDF → spatial extract). Extend `document-translator check` for LibreOffice/ImageMagick when this path is enabled.
- **EPUB / HTML input** — New in-house extractors (not covered by LiteParse).

## Layout, export & provenance

- **Table and image preservation** — Export loses layout today; layout-preserving LiteParse text is the upstream prerequisite; Pandoc export remains in-house.
- **RTL export (Arabic, Hebrew)** — `ar` in display names but no RTL CSS/PDF direction.
- **Style preservation from original** — Fonts, headings, and document styling carried through export where Pandoc/conversion allows.

## Translation quality

- **Glossary / terminology** — Brand names, legal defined terms, do-not-translate lists.
- **Resume from checkpoint** — Large docs fail mid-translation → full re-run; needs stage persistence + idempotent chunk cache. Persist extracted markdown per page chunk (and page map when `--target-pages` is used) as an early checkpoint artifact.

## Quality, testing & ops

- **Extraction evaluation harness** — Adapt LiteParse `dataset_eval_utils` pattern: `tools/extract-eval/` with pluggable backends (`pymupdf`, `liteparse`); score extract QA **before** translation LLM cost.
- **Golden extraction regression suite** — Curated anonymized corpus; CI compares normalized extract output on `extract/` changes.
- **Extend `document-translator check`** — Verify LiteParse extra when `--extract-backend liteparse`; LibreOffice/ImageMagick for office/image formats; OCR server reachability when URL configured.

## CLI & developer experience

- **`--no-translate` extract parity** — Full extract flags on extract-only runs (`--target-pages`, `--pdf-ocr-server-url`, `--extract-backend`, `--dpi`, `--pdf-password`).
- **Extraction architecture docs** — “Adding an extract backend” section in `AGENTS.md` (interface contract, routing rules, when to use LiteParse vs pymupdf).

## Shipped in 0.1.0

- OCR for scanned PDFs — Tesseract-backed per-page fallback when native PDF text is sparse (`--no-pdf-ocr` to disable)
- Quick run mode (`--mode quick`, default) and thorough dual-pass verification (`--mode thorough`)
- Dual-pass translation with discrepancy reconciliation
- Multi-format extraction and export (`pdf`, `docx`, `doc`, `odt`, `rtf`, `txt`, `md`)
- Configurable target language (`--target-lang`)
- Subprocess-first CLI with Laravel integration guide
- Docker image distribution (all LLM provider extras pre-installed)
- Batch translate, preflight `check`, job timeout/cancellation, webhooks, and `metadata.llm_usage`

## Explicitly out of scope

**Product scope (translation-first):**

- Full Rust rewrite of the pipeline or WASM/browser distribution
- Node.js / napi-rs package; JSON/text as primary deliverable instead of Pandoc documents
- Grid-projection export fidelity as a near-term goal (long-term layout work stays separate from translation)
- Vision QA ground-truth dataset generation (`lp-process`-style) unless building a public benchmark program
- Bundled Tesseract inside Python wheels (keep system/Docker Tesseract documented)

**Extraction scope (use LiteParse, don't recreate):**

- Spatial PDF parsing, grid projection, or selective OCR merge in Python
- Standalone LibreOffice → PDF conversion router duplicating LiteParse `conversion.rs` (use LiteParse for PPTX/XLSX/images instead)
- Making `liteparse` a required dependency (stays optional extra unless benchmarks prove otherwise)

Track progress via [GitHub Issues](https://github.com/AragusNZ/tool-ai-document-translator/issues).
