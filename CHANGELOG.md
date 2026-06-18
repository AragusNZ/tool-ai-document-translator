# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- Checkpoint resume with `--preserve-layout` now restores layout translation source from `artifacts/checkpoints/extract/layout-body.md` instead of failing with `CHECKPOINT_MISMATCH`

### Added

- EPUB and HTML input extraction (`extract/epub.py`, `extract/html.py`); export formats `epub` and `html` via Pandoc
- RTL export for Arabic (`ar`) and Hebrew (`he`) targets: `translation-rtl.css` for PDF, `lang` metadata for Pandoc exports
- `--preserve-layout` / `preserve_layout` config: translate LiteParse `layout_text` when available (`JobMetadata.used_layout_text`)
- `IssueCode.PRESERVE_LAYOUT_UNAVAILABLE` when layout source is requested but not provided by the extractor
- Glossary support: `--glossary` / `glossary_path` / inline `glossary` in `--config`; terms injected into translation prompts and reconcile protected-token checks
- Checkpoint resume: `--resume` flag, `artifacts/checkpoint.json`, per-chunk `artifacts/checkpoints/` cache; failed jobs retain checkpoints for incremental retry
- `artifact_availability` keys `checkpoint_json` and `checkpoints_dir`; `JobMetadata.glossary_term_count` and `resumed_from_checkpoint`
- Golden extraction regression suite (`tests/fixtures/extract/`, `tests/test_extract_regression.py`) with SHA-256 normalized text hashes; `requires_liteparse` marker and scheduled LiteParse CI workflow
- Extract eval harness HTML reports and QA pass-rate scoring (`--qa`, `--report` on `python -m tools.extract_eval.benchmark`)
- [docs/extract-backend-routing.md](docs/extract-backend-routing.md) — recommended `--extract-backend` per input format (PyMuPDF remains default for PDF in `auto`)
- HTTP OCR client (`extract/ocr_http.py`) implementing the LiteParse `POST /ocr` API for PyMuPDF sparse-page OCR and LiteParse backend passthrough
- `pdf_ocr_server_url`, `pdf_ocr_workers`, and `extract_debug` in `PipelineConfig` / `--config` JSON; CLI flags `--pdf-ocr-server-url`, `--pdf-ocr-workers`, `--extract-debug`
- Concurrent per-page OCR in the PyMuPDF backend (thread pool; default `min(4, cpu-1)` workers)
- `check` preflight probe for configured HTTP OCR servers (`pdf_ocr_server` check)
- Per-page extract debug logging and Sentry breadcrumbs on the extract stage
- LiteParse spatial extraction sidecars: `artifacts/01-extraction-layout.json` and optional `artifacts/screenshots/` (retained when `keep_work_files` is set)
- Extract CLI/config options: `--target-pages`, `--pdf-password`, `--extract-dpi`, `--extract-screenshots` (LiteParse backend; pymupdf emits `EXTRACT_OPTION_IGNORED` warnings)
- `JobMetadata.extract_backend` and `extract_page_stats` in terminal JSON payloads
- `artifact_availability` keys `extraction_layout_json` and `screenshots_dir`
- Input formats via LiteParse (optional `[extract-liteparse]`): `.pptx`, `.ppt`, `.xlsx`, `.xls`, `.png`, `.jpg`, `.jpeg`, `.tiff`, `.webp` — routed in `auto` mode; default export is `pdf`
- `check` preflight: `liteparse`, `libreoffice`, and `imagemagick` checks when `--extract-backend` is `liteparse` (required) or `auto` (warn)
- `tools/extract_eval/` benchmark harness with pluggable providers (`python -m tools.extract_eval.benchmark`)
- [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) — optional LiteParse (Apache-2.0) attribution, PDFium note, and sample-document licensing guidance
- Docker `WITH_LITEPARSE=1` build arg to bundle `[extract-liteparse]` with third-party notice documentation
- Pluggable extraction backends (`extract/backends/`): PyMuPDF (default) and optional LiteParse via `[extract-liteparse]` extra
- `--extract-backend {auto,pymupdf,liteparse}` on `translate` and `check`; `extract_backend` in `PipelineConfig` / `--config` JSON; env `DOCUMENT_TRANSLATOR_EXTRACT_BACKEND`
- `tools/extract_eval/` benchmark spike for comparing pymupdf vs liteparse extraction
- `job_id` validation and `runs_dir` containment checks to block path traversal
- Webhook SSRF guards and optional `webhook_https_only` config
- Input hardening: reject symlinks and directories; enforce `max_input_bytes` (default 20 MB)
- Subprocess timeouts (`subprocess_timeout_seconds`) for pandoc, LibreOffice, and PDF export
- Per-LLM request timeout (`llm_request_timeout_seconds`) for OpenAI, Anthropic, and Google clients
- Webhook delivery retries with exponential backoff (`webhook_max_retries`, `webhook_retry_base_delay`)
- `--no-translate` flag to skip translation and export extracted text (extraction and detection still run)
- `--save-resolved` flag to retain `04-resolved.md` as a terminal artifact (`artifacts.resolved_md` in JSON API)
- `--no-cover-page` flag to export the document body without the cover page
- CI: Python 3.11/3.12 matrix, ruff lint, pip-audit, Trivy image scan on release, workflow deduplication
- `requirements-lock.txt` for pinned dependency installs; Docker base image digest pin
- Pre-commit hooks (ruff + fast pytest) and Dependabot config
- Expanded [SECURITY.md](SECURITY.md) (job IDs, webhooks, config validation, data egress)

### Changed

- PyMuPDF sparse-page OCR threshold raised from 20 to 25 characters per page
- Job artifact directories created with mode `0700`
- Subprocess stderr in user-facing errors is sanitized and truncated
- README clarifies that intermediate working files are not kept on failure unless `keep_work_files` is set
- Release script pytest gate runs `pytest -m "not integration"` (aligned with dev workflow)

### Fixed

- Docker CI no longer pushes to GHCR on every `main` commit; image publish runs on `v*` tags only, with smoke tests on PRs and `main`

## [0.1.0] - 2026-06-17

Initial Release
