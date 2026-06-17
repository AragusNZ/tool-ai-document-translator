# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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

- `--config` JSON merges through `PipelineConfig.model_validate` instead of raw `setattr`
- Job artifact directories created with mode `0700`
- Subprocess stderr in user-facing errors is sanitized and truncated
- README clarifies that intermediate working files are not kept on failure unless `keep_work_files` is set
- Release script pytest gate runs `pytest -m "not integration"` (aligned with dev workflow)

### Fixed

- Docker CI no longer pushes to GHCR on every `main` commit; image publish runs on `v*` tags only, with smoke tests on PRs and `main`

## [0.1.0] - 2026-06-17

Initial Release
