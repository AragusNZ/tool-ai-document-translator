# Contributing

Thank you for contributing to document-translator.

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,monitoring]"

# System tools (Debian/Ubuntu)
sudo apt install pandoc libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 libffi-dev shared-mime-info
```

## Before opening a PR

1. Run tests with coverage:

```bash
pytest --cov=document_translator --cov-report=term-missing --cov-fail-under=85
```

2. **Audit [README.md](README.md)** — update any section that is now inaccurate.

3. **Add a [CHANGELOG.md](CHANGELOG.md) entry** under `## [Unreleased]` for user-visible changes.

4. If you change the CLI contract (exit codes, artifacts, JSON API), follow [.cursor/skills/cli-contract-change/SKILL.md](.cursor/skills/cli-contract-change/SKILL.md) and update [docs/integration/Laravel.md](docs/integration/Laravel.md).

See [versioning policy](.cursor/docs/versioning.md) for semver rules.

## Pull request guidelines

- Keep diffs focused; match existing code style (`from __future__ import annotations`, Pydantic models, `MockLLMClient` in tests).
- Do not commit secrets (`CURSOR_API_KEY`, Sentry DSN values).
- Do not bump `pyproject.toml` version unless explicitly coordinating a release.
