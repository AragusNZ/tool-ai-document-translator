# Laravel integration

Laravel handles HTTP, auth, uploads, and queuing. Python handles document processing via subprocess.

## Flow

1. Client uploads file to Laravel API
2. Laravel runs `document-translator check` (optional but recommended) before accepting uploads
3. Laravel stores file, creates `job_id`, dispatches queue job
4. Queue worker runs Python CLI
5. Client polls `GET /translations/{job_id}` reading `status.json` / `metadata.json`

## Queue job example

```php
use Symfony\Component\Process\Process;

$process = new Process([
    config('document-translator.python'),  // e.g. /path/to/venv/bin/python
    '-m', 'document_translator',
    'translate',
    $inputPath,
    '--job-id', $this->jobId,
    '--output-dir', config('document-translator.runs_dir'),
    '--format', 'json',
    '--target-lang', $this->targetLang,  // e.g. en (default), es, fr, de
    '--source-lang', $this->sourceLang,  // optional ISO 639-1 override, e.g. es
    '--translation-context', $this->translationContext,  // optional, e.g. contract parties
    '--export-format', $this->exportFormat,  // e.g. pdf, docx; omit to match input extension
    '--llm', $this->llm,  // e.g. cursor:composer-2.5 (default), openai:gpt-4o
    '--mode', $this->translationMode,  // quick (default) or thorough (dual-pass verification)
    '--timeout', (string) config('document-translator.job_timeout', 3600),
    '--webhook-url', config('document-translator.webhook_url'),
    '--webhook-secret', config('document-translator.webhook_secret'),
]);
// Laravel Process timeout sends SIGTERM; CLI finalizes status.json with JOB_CANCELLED when possible.
// Use a value slightly above --timeout so the Python cooperative timeout fires first.
$process->setTimeout((int) config('document-translator.job_timeout', 3600) + 60);
$exitCode = $process->run();

$output = json_decode($process->getOutput(), true);
// Exit 0 = completed, 3 = completed_with_warnings (check artifact_availability.final_output)
// Terminal API payload: metadata.json (includes summary, discrepancies, issues)
// User download: artifacts/05-final.{ext}
if ($exitCode === 2) {
    throw new \RuntimeException($output['error_message'] ?? 'Translation failed');
}
```

## Batch translate

When a user uploads multiple files, run one subprocess instead of one per file. Each input still gets its own `job_id` and `runs/{job_id}/` tree for polling.

```php
$argv = [
    config('document-translator.python'),
    '-m', 'document_translator',
    'translate',
];
foreach ($this->uploads as $upload) {
    $argv[] = $upload->storedPath;
}
$argv = array_merge($argv, [
    '--job-ids', ...array_column($this->uploads, 'jobId'),
    '--output-dir', config('document-translator.runs_dir'),
    '--format', 'json',
    '--target-lang', $this->targetLang,
    '--llm', config('document-translator.llm'),
]);

$process = new Process($argv);
$process->setTimeout((int) config('document-translator.job_timeout', 3600) * count($this->uploads) + 60);
$exitCode = $process->run();

$batch = json_decode($process->getOutput(), true);
// $batch['status'] — aggregate worst status
// $batch['jobs'] — array of JobResult payloads (same shape as single-file JSON)
foreach ($batch['jobs'] as $job) {
    // Update DB row for $job['job_id']; poll runs/{job_id}/status.json as fallback
}
```

Exit codes for batch: `2` if any job failed, `3` if any completed with warnings and none failed, `0` if all completed cleanly.

## Laravel config (`config/document-translator.php`)

```php
return [
    'python' => env('DOCUMENT_TRANSLATOR_PYTHON', base_path('../document-translator/.venv/bin/python')),
    'runs_dir' => env('DOCUMENT_TRANSLATOR_RUNS_DIR', storage_path('app/translations/runs')),
    'llm' => env('DOCUMENT_TRANSLATOR_LLM', 'cursor:composer-2.5'),
    'job_timeout' => (int) env('DOCUMENT_TRANSLATOR_JOB_TIMEOUT', 3600),
    'webhook_url' => env('DOCUMENT_TRANSLATOR_WEBHOOK_URL'),
    'webhook_secret' => env('DOCUMENT_TRANSLATOR_WEBHOOK_SECRET'),
];
```

## Webhook callback

On terminal status (`completed`, `completed_with_warnings`, or `failed`), the CLI POSTs a JSON payload to `--webhook-url` after `metadata.json` and `status.json` are written. This reduces polling load on Laravel.

Payload shape:

```json
{
  "event": "job.terminal",
  "job": { "...": "JobResult.model_dump_json_api()" }
}
```

When `--webhook-secret` is set, the request includes header `X-Document-Translator-Signature: sha256=<hmac>` where the HMAC is computed over the raw JSON body with SHA-256.

Laravel verification example:

```php
$signature = $request->header('X-Document-Translator-Signature');
$expected = 'sha256=' . hash_hmac('sha256', $request->getContent(), config('document-translator.webhook_secret'));
if (! hash_equals($expected, $signature ?? '')) {
    abort(401);
}
$payload = $request->json()->all();
// $payload['event'] === 'job.terminal'
// $payload['job']['job_id'], status, artifact_availability, metadata, ...
```

Webhook delivery failures add `WEBHOOK_FAILED` to `metadata.issues` and may upgrade the job to `completed_with_warnings` (exit `3`). `status.json` is updated with the new `issue_count`. Polling remains a valid fallback.

## Preflight check

Run before accepting uploads or on a health endpoint:

```php
$check = new Process([
    config('document-translator.python'),
    '-m', 'document_translator',
    'check',
    '--format', 'json',
    '--output-dir', config('document-translator.runs_dir'),
    '--llm', config('document-translator.llm'),
    '--export-format', 'pdf',
]);
$check->run();
if ($check->getExitCode() !== 0) {
    // Host not ready — reject uploads or return 503
}
```

## Shared infrastructure

- `runs/` directory readable by both Laravel and the queue worker
- API key for the selected LLM provider in the queue worker environment (secrets manager, not committed `.env`):
  - Default (`cursor:composer-2.5`): `CURSOR_API_KEY`
  - `openai:*`: `OPENAI_API_KEY` — included in the published Docker image; for host venv: `pip install document-translator[openai]`
  - `anthropic:*`: `ANTHROPIC_API_KEY` — included in the published Docker image; for host venv: `pip install document-translator[anthropic]`
  - `google:*`: `GOOGLE_API_KEY` — included in the published Docker image; for host venv: `pip install document-translator[google]`
- List supported selectors: `python -m document_translator list-llms` (or `document-translator list-llms`)
- Preflight: `document-translator check --format json` (exit `0` = ready)
- Job timeout: pass `--timeout` to the translate command; set `DOCUMENT_TRANSLATOR_JOB_TIMEOUT` in the worker env
- Long-running jobs: set `Process::setTimeout()` slightly above `--timeout` so SIGTERM cancels cleanly (`JOB_CANCELLED` in `status.json`)
- Billing: read `metadata.json` → `llm_usage.input_tokens`, `llm_usage.output_tokens`, `llm_usage.estimated_cost_usd` (indicative pricing for known models)
- Webhook: pass `--webhook-url` (and `--webhook-secret`) for terminal callbacks; verify `X-Document-Translator-Signature` in your API route

## Observability

- **Logging**: CLI configures `document_translator` logging on startup. Set `DOCUMENT_TRANSLATOR_LOG_FORMAT=json` to emit structured JSON on stderr (useful when Laravel captures subprocess stderr).
- **Sentry (Python)**: Set `SENTRY_DSN` or `DOCUMENT_TRANSLATOR_SENTRY_DSN` in the queue worker environment. Install `document-translator[monitoring]` in the Python venv. Each CLI invocation is one Sentry transaction (`document_translator.translate`).
- **Dual Sentry**: Laravel PHP Sentry covers API/queue orchestration; Python Sentry covers pipeline internals. They can share one Sentry project or use separate DSNs.
- **Warnings as events**: To report export failures to Sentry, set `DOCUMENT_TRANSLATOR_SENTRY_REPORT_SEVERITIES=error,warn`.

Example queue worker env:

```bash
export SENTRY_DSN="https://..."
export DOCUMENT_TRANSLATOR_SENTRY_ENVIRONMENT=production
export DOCUMENT_TRANSLATOR_LOG_FORMAT=json
export DOCUMENT_TRANSLATOR_SENTRY_REPORT_SEVERITIES=error,warn
```

## Docker alternative

Instead of a host Python venv, the queue worker can run the published GHCR image via `docker run`. The image includes all LLM provider packages — pass `--llm` and the matching API key env var. Volume mounts, exit codes, and a PHP `Process` example: [Docker.md](Docker.md).

## Database sketch

| Column | Type | Notes |
|--------|------|-------|
| `job_id` | uuid | Primary external identifier |
| `user_id` | bigint | Owner |
| `status` | string | Mirror of `status.json` stage |
| `original_filename` | string | |
| `error_message` | text | Nullable |
