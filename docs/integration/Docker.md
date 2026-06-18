# Docker integration

Run document-translator as a containerized CLI for queue workers, cron, or manual jobs.

The published image installs **all LLM provider extras** (`cursor-sdk`, `openai`, `anthropic`, `google-genai`) plus `[monitoring]`. Pass `--llm provider:model` and the matching API key at runtime — no custom image layer is required for provider choice.

## Build

```bash
docker build -t document-translator .
```

### LiteParse backend (optional)

The default image does **not** include LiteParse. To bundle the optional `[extract-liteparse]` extra (Apache-2.0; see [THIRD_PARTY_NOTICES.md](../../THIRD_PARTY_NOTICES.md)):

```bash
docker build --build-arg WITH_LITEPARSE=1 -t document-translator:liteparse .
```

Use `--extract-backend liteparse` (or `auto` with office/image inputs once Phase 2 formats land) at runtime. Retain third-party license notices when distributing this image variant.

## Preflight

Verify the container can run jobs before accepting uploads:

```bash
docker run --rm \
  -e OPENAI_API_KEY \
  -v "$(pwd)/runs:/runs" \
  document-translator check \
    --format json \
    --output-dir /runs \
    --llm openai:gpt-4o \
    --export-format pdf
```

Exit `0` = ready; `1` = missing dependency or API key.

## Run (Cursor, default)

Mount input files and a writable runs directory:

```bash
export CURSOR_API_KEY="your-key-here"

docker run --rm \
  -e CURSOR_API_KEY \
  -v "$(pwd)/input:/input:ro" \
  -v "$(pwd)/runs:/runs" \
  document-translator translate /input/document.pdf \
    --job-id "$(uuidgen)" \
    --output-dir /runs \
    --format json
```

## Run (OpenAI / Anthropic / Google)

Pass `--llm` and the provider env var. The image already includes the Python packages.

```bash
# OpenAI
docker run --rm \
  -e OPENAI_API_KEY \
  -v "$(pwd)/input:/input:ro" \
  -v "$(pwd)/runs:/runs" \
  document-translator translate /input/document.pdf \
    --job-id "$(uuidgen)" \
    --output-dir /runs \
    --llm openai:gpt-4o \
    --format json

# Anthropic
docker run --rm \
  -e ANTHROPIC_API_KEY \
  -v "$(pwd)/input:/input:ro" \
  -v "$(pwd)/runs:/runs" \
  document-translator translate /input/document.pdf \
    --llm anthropic:claude-sonnet-4-6 \
    --format json

# Google Gemini
docker run --rm \
  -e GOOGLE_API_KEY \
  -v "$(pwd)/input:/input:ro" \
  -v "$(pwd)/runs:/runs" \
  document-translator translate /input/document.pdf \
    --llm google:gemini-2.5-flash \
    --format json
```

List supported selectors:

```bash
docker run --rm document-translator list-llms
```

The image includes Tesseract for scanned PDF OCR; pass `--no-pdf-ocr` to disable.

The container working directory is `/runs`. Artifacts are written to `/runs/{job_id}/`.

## Exit codes

Same as the host CLI:

| Code | Meaning |
|------|---------|
| `0` | Completed |
| `1` | Startup/config error |
| `2` | Pipeline failed |
| `3` | Completed with warnings |

With `--format json`, stdout contains `JobResult.model_dump_json_api()` for orchestrators.

## Export format

```bash
docker run --rm -e CURSOR_API_KEY \
  -v "$(pwd)/input:/input:ro" \
  -v "$(pwd)/runs:/runs" \
  document-translator translate /input/report.docx \
    --job-id "$(uuidgen)" \
    --output-dir /runs \
    --export-format pdf
```

## Target language

```bash
docker run ... document-translator translate /input/doc.pdf \
  --target-lang de \
  ...
```

## Job timeout

```bash
docker run --rm -e OPENAI_API_KEY \
  -v "$(pwd)/input:/input:ro" \
  -v "$(pwd)/runs:/runs" \
  document-translator translate /input/document.pdf \
    --llm openai:gpt-4o \
    --timeout 3600 \
    --format json
```

## Laravel queue worker

Instead of a host Python venv, invoke the container from your queue job:

```php
use Symfony\Component\Process\Process;

$llm = config('document-translator.llm', 'cursor:composer-2.5');
$apiKeyEnv = match (explode(':', $llm, 2)[0]) {
    'openai' => 'OPENAI_API_KEY',
    'anthropic' => 'ANTHROPIC_API_KEY',
    'google' => 'GOOGLE_API_KEY',
    default => 'CURSOR_API_KEY',
};

$process = new Process([
    'docker', 'run', '--rm',
    '-e', $apiKeyEnv . '=' . config('document-translator.api_keys.' . explode(':', $llm, 2)[0]),
    '-v', $inputPath . ':/input/' . basename($inputPath) . ':ro',
    '-v', config('document-translator.runs_dir') . ':/runs',
    config('document-translator.docker_image', 'ghcr.io/aragusnz/tool-ai-document-translator:latest'),
    'translate',
    '/input/' . basename($inputPath),
    '--job-id', $this->jobId,
    '--output-dir', '/runs',
    '--format', 'json',
    '--llm', $llm,
    '--timeout', (string) config('document-translator.job_timeout', 3600),
]);
$process->setTimeout((int) config('document-translator.job_timeout', 3600) + 60);
$exitCode = $process->run();
```

Ensure the queue worker can access the Docker socket and that `runs/` is on a volume shared with your API for polling.

## GitHub Container Registry

Released images are published to:

```
ghcr.io/aragusnz/tool-ai-document-translator:<version>
ghcr.io/aragusnz/tool-ai-document-translator:latest
```

Pull a release:

```bash
docker pull ghcr.io/aragusnz/tool-ai-document-translator:0.5.0
```

## Observability

Set `DOCUMENT_TRANSLATOR_LOG_FORMAT=json` to emit structured logs on stderr for log aggregation:

```bash
docker run --rm -e CURSOR_API_KEY -e DOCUMENT_TRANSLATOR_LOG_FORMAT=json ...
```

Optional Sentry (image includes `[monitoring]`):

```bash
docker run --rm -e CURSOR_API_KEY -e SENTRY_DSN -e DOCUMENT_TRANSLATOR_SENTRY_ENVIRONMENT=production ...
```

## Cursor-only slim image (optional)

To build a smaller image with Cursor only (no OpenAI/Anthropic/Google packages), change the install line in `Dockerfile`:

```dockerfile
RUN pip install --upgrade pip && pip install ".[monitoring]"
```

The default published GHCR image uses all provider extras for SaaS deployments that offer model choice.
