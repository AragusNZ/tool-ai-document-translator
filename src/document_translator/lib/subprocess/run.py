from __future__ import annotations

import subprocess
from collections.abc import Sequence

from document_translator.config.defaults import DEFAULT_SUBPROCESS_TIMEOUT_SECONDS
from document_translator.lib.subprocess.sanitize import sanitize_subprocess_detail


def run_checked(
    cmd: Sequence[str],
    *,
    timeout_seconds: float = DEFAULT_SUBPROCESS_TIMEOUT_SECONDS,
    label: str = "subprocess",
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            list(cmd),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"{label} timed out after {timeout_seconds:g}s") from exc

    if result.returncode != 0:
        detail = sanitize_subprocess_detail(result.stderr or result.stdout or "unknown error")
        raise RuntimeError(f"{label} failed: {detail}")
    return result
