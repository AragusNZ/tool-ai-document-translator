# Gaps and follow-up work

Tracked deferrals after Phase 7 (export, layout, and remaining formats). Normative contract remains [README.md](README.md) and [.cursor/docs/cli-contract.md](.cursor/docs/cli-contract.md).

## Post-roadmap / incremental quality

- **Table and image layout fidelity** — `--preserve-layout` uses LiteParse `layout_text` for translation only; export still flows through Pandoc markdown (no grid-table experiments yet)
- **RTL DOCX fidelity** — PDF/HTML use RTL CSS; DOCX relies on Pandoc `lang` metadata only (no custom reference template)
- **EPUB/HTML extract edge cases** — complex CSS, embedded fonts, and multi-file HTML sites not covered by golden fixtures
- **Vision QA pipeline** — deferred from Phase 5 (`lp-process` ground-truth)

## Phase 6 known limitations

- **Checkpoint scope** — per-chunk translation cache only; reconcile and export stages re-run on resume (no reconcile checkpoint)
- **Resume requires same job directory** — `--job-id` must match the failed run; no cross-job migration
- **Glossary is prompt + token heuristic** — no bbox/layout-span linking; preferred terms enforced via protected-token compare, not structured post-edit
- **Inline glossary in env** — terminology via `glossary` key in `--config` JSON only (not `DOCUMENT_TRANSLATOR_GLOSSARY` env)
- **Thorough mode pass 2** — resumes from cached chunks but always re-runs reconcile when both passes complete

## Phase 5 known limitations

- **Golden fixture scope** — 8 programmatic PDFs only; no office/image/spatial/OCR golden cases yet
- **LiteParse golden is scheduled** — not gated on every PR (requires `[extract-liteparse]` + system deps)
- **Benchmark QA** — hash and char-count checks only; no vision QA or ground-truth document QA pipeline
- **No LiteParse default for PDF** — `auto` still routes `.pdf` to PyMuPDF; revisit when expanded fixtures show clear wins

## Phase 4 known limitations

- **HTTP OCR fallback chain** — when `pdf_ocr_server_url` is set, HTTP OCR is used exclusively for sparse pages (Tesseract is not tried as fallback on HTTP failure)
- **Per-page duration** — `extract_page_stats` still omits timing for pymupdf and liteparse paths
- **OCR probe payload** — `check` sends a 1×1 PNG to `POST /ocr`; some servers may reject tiny images even when healthy for real pages
- **No bundled OCR server** — EasyOCR/PaddleOCR compose is documented only; not shipped in-repo
- **LiteParse `ocr_merge` heuristics** — not ported; pymupdf uses simple text merge from OCR API results only

## Carried from Phase 3

- **PyMuPDF `target_pages`** — warns and ignores; no native page limiting on the default PDF path
- **Sidecars are working artifacts** — removed on finalize unless `keep_work_files`
- **No committed spatial/office fixtures** — OCR and layout tests rely on mocks or local tools

## Carried from Phase 2

- **`check` is config-based** — does not accept input paths for format-specific preflight
