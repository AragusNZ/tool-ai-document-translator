# Security policy

## Reporting a vulnerability

Please report security issues via [GitHub Security Advisories](https://github.com/AragusNZ/tool-ai-document-translator/security/advisories/new) rather than public issues.

Include:

- Description of the vulnerability and impact
- Steps to reproduce
- Affected versions

We will acknowledge reports as quickly as possible and coordinate a fix before public disclosure when appropriate.

## Secrets

- Never commit `CURSOR_API_KEY`, `SENTRY_DSN`, `WEBHOOK_SECRET`, or other credentials.
- Pass API keys via environment variables or your platform's secrets manager.
- Prefer `DOCUMENT_TRANSLATOR_WEBHOOK_SECRET` (env) over `--webhook-secret` on the command line — argv is visible in process listings.
- Queue workers and Docker containers should receive API keys at runtime, not bake them into images.

## Untrusted input

The CLI processes arbitrary document files from disk. Run workers with least privilege, isolate job directories, and treat uploaded files as untrusted input.

### Job identifiers

`--job-id` and `--job-ids` must be 1–128 characters and use only letters, digits, underscores, and hyphens. Values are validated so they cannot escape the configured `runs_dir`. Auto-generated UUIDs satisfy this constraint.

### Input files

- Symlinks are rejected.
- Directories and non-regular files are rejected.
- Input size is capped by `max_input_bytes` in config (default 20 MB, from `LARGE_INPUT_BYTES`).

### Configuration

`--config` JSON is validated through `PipelineConfig` (Pydantic), including `webhook_url` scheme checks and SSRF guards. Do not store API keys in world-readable config files.

## Webhooks

- `webhook_url` must use `http://` or `https://` and must not target localhost, private networks, or link-local addresses.
- Set `webhook_https_only: true` in config to require HTTPS in production.
- Terminal webhooks POST the full `JobResult` JSON API payload (including document-derived metadata). Classify data before enabling webhooks.
- Delivery is retried with exponential backoff; integrators should still poll `status.json` as the source of truth.

## Data egress

Document text, `translation_context`, discrepancy spans, and issue details are sent to:

- The configured LLM provider (Cursor, OpenAI, Anthropic, or Google) during translation and detection
- The configured webhook URL on job completion (when set)
- Optional Sentry (errors and configured severities only)

Review provider and webhook policies before processing regulated or confidential material.

## Artifact storage

Job directories are created with mode `0700`. By default, intermediate working files are removed after completion; only `status.json`, `metadata.json`, and the final export remain unless `keep_work_files: true`.
