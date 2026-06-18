# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- OCR for scanned PDFs — Tesseract-backed per-page fallback when native PDF text is sparse (`--no-pdf-ocr` to disable)
- Quick run mode (`--mode quick`, default) and thorough dual-pass verification (`--mode thorough`)
- Dual-pass translation with discrepancy reconciliation
- Multi-format extraction and export (`pdf`, `docx`, `doc`, `odt`, `rtf`, `txt`, `md`)
- Configurable target language (`--target-lang`)
- Subprocess-first CLI with Laravel integration guide
- Docker image distribution (all LLM provider extras pre-installed)
- Batch translate, preflight `check`, job timeout/cancellation, webhooks, and `metadata.llm_usage`
