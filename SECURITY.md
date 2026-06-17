# Security policy

## Reporting a vulnerability

Please report security issues via [GitHub Security Advisories](https://github.com/AragusNZ/tool-ai-document-translator/security/advisories/new) rather than public issues.

Include:

- Description of the vulnerability and impact
- Steps to reproduce
- Affected versions

We will acknowledge reports as quickly as possible and coordinate a fix before public disclosure when appropriate.

## Secrets

- Never commit `CURSOR_API_KEY`, `SENTRY_DSN`, or other credentials.
- Pass API keys via environment variables or your platform's secrets manager.
- Queue workers and Docker containers should receive `CURSOR_API_KEY` at runtime, not bake it into images.

## Untrusted input

The CLI processes arbitrary document files from disk. Run workers with least privilege, isolate job directories, and treat uploaded files as untrusted input.
