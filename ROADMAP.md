# Roadmap

Planned improvements beyond the current `0.1.0` release. Not committed to a timeline.

## Planned
 - Resume from checkpoint: Large docs fail mid-translation → full re-run; would need stage persistence + idempotent chunk cache
 - Glossary / terminology: Brand names, legal defined terms, do-not-translate lists
 - Style preservation from original.

### Support for
 - EPUB / HTML input: Common e-book and web-content sources
 - PPTX / XLSX: Business docs with slides/tables
 - Table and image preservation: Export loses layout; text-only markdown intermediate
 - RTL export (Arabic, Hebrew): ar in display names but no RTL CSS/PDF direction

## Shipped in 0.1.0

- OCR for scanned PDFs — Tesseract-backed per-page fallback when native PDF text is sparse (`--no-pdf-ocr` to disable)
- Quick run mode (`--mode quick`, default) and thorough dual-pass verification (`--mode thorough`)
- Dual-pass translation with discrepancy reconciliation
- Multi-format extraction and export (`pdf`, `docx`, `doc`, `odt`, `rtf`, `txt`, `md`)
- Configurable target language (`--target-lang`)
- Subprocess-first CLI with Laravel integration guide
- Docker image distribution (all LLM provider extras pre-installed)
- Batch translate, preflight `check`, job timeout/cancellation, webhooks, and `metadata.llm_usage`

Track progress via [GitHub Issues](https://github.com/AragusNZ/tool-ai-document-translator/issues).
