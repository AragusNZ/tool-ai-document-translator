from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from document_translator import __version__

ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str, env: dict[str, str] | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    import os

    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        [sys.executable, "-m", "document_translator", *args],
        cwd=cwd or ROOT,
        capture_output=True,
        text=True,
        env=merged,
    )


def test_subprocess_version() -> None:
    result = run_cli("--version")
    assert result.returncode == 0
    assert __version__ in result.stdout


def test_subprocess_list_llms_json() -> None:
    result = run_cli("list-llms", "--format", "json")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert isinstance(payload, list)
    assert payload
    assert "id" in payload[0]


def test_subprocess_translate_missing_input_exits_1(tmp_path: Path) -> None:
    result = run_cli(
        "translate",
        str(tmp_path / "missing.txt"),
        "--job-id",
        "subprocess-missing",
        "--output-dir",
        str(tmp_path / "runs"),
    )
    assert result.returncode == 1


def test_subprocess_check_json(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    runs.mkdir()
    result = run_cli(
        "check",
        "--format",
        "json",
        "--output-dir",
        str(runs),
        env={
            "CURSOR_API_KEY": "",
            "OPENAI_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
            "GOOGLE_API_KEY": "",
        },
    )
    assert result.returncode in {0, 1}
    payload = json.loads(result.stdout)
    assert "checks" in payload
    assert isinstance(payload["checks"], list)
