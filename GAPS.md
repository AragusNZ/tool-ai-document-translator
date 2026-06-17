# Gaps and follow-up work

Tracked deferrals after Phase 3 (spatial artifacts and extract flags). Normative contract remains [README.md](README.md) and [.cursor/docs/cli-contract.md](.cursor/docs/cli-contract.md).

## Phase 4 — PyMuPDF OCR and observability

- HTTP OCR client (`pdf_ocr_server_url`) per LiteParse OCR API spec
- Concurrent page OCR in pymupdf backend
- `DOCUMENT_TRANSLATOR_EXTRACT_DEBUG` structured logging
- Sentry breadcrumbs on extract stage
- OCR server health probe in `check`

## Phase 5 — Quality gates

- Golden extraction regression suite (`tests/fixtures/extract/`, `test_extract_regression.py`)
- CI gate on pymupdf golden; optional liteparse workflow
- HTML benchmark reports in `tools/extract_eval/`
- Default routing decision doc (when to prefer liteparse per format)

## Phase 6+ — Translation and export

- Glossary / terminology in translate + reconcile
- Checkpoint resume with per-chunk artifacts
- EPUB/HTML extractors; RTL export; layout-preserving export (`--preserve-layout` using `layout_text`)

## Phase 3 known limitations

- **`layout_text` not used as translation source** — extraction stores layout-preserving page text, but translation still uses flat `01-extracted.md` body; `--preserve-layout` export is Phase 7
- **Reconcile protected-token scope** — layout span linking for glossary/bbox-aware reconciliation not wired
- **Per-page duration** — `extract_page_stats` omits timing; LiteParse does not expose per-page parse duration in the Python API
- **PyMuPDF `target_pages`** — warns and ignores; no native page limiting on the default PDF path
- **Sidecars are working artifacts** — `01-extraction-layout.json` and `screenshots/` are removed on finalize unless `keep_work_files`; not in top-level `artifacts` path map (only `artifact_availability`)
- **Screenshots require LiteParse** — pymupdf path does not render page images
- **No committed office/image/spatial fixtures** — spatial tests mock LiteParse; end-to-end layout jobs need local `[extract-liteparse]`

## Carried from Phase 2

- **`check` is config-based** — does not accept input paths for format-specific preflight
- **`auto` preflight** — LiteParse stack checks warn only; failure surfaces at extraction time for office/image inputs
- **Export default** — office/image inputs default to `pdf` export
- **Benchmark harness** — latency + char counts only; no QA scoring or CI gate yet
