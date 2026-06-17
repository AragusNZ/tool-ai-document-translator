from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from document_translator.lib.subprocess.run import run_checked


def require_pandoc() -> None:
    if shutil.which("pandoc") is None:
        raise RuntimeError("pandoc not found on PATH. Install with: sudo apt install pandoc")


def run_pandoc_to_markdown(
    input_path: Path,
    *,
    timeout_seconds: float | None = None,
) -> str:
    require_pandoc()

    with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as tmp:
        out_path = Path(tmp.name)

    try:
        cmd = ["pandoc", str(input_path), "-t", "markdown", "-o", str(out_path), "--wrap=none"]
        kwargs: dict[str, float] = {}
        if timeout_seconds is not None:
            kwargs["timeout_seconds"] = timeout_seconds
        run_checked(cmd, label="pandoc conversion", **kwargs)
        return out_path.read_text(encoding="utf-8", errors="ignore").strip() + "\n"
    finally:
        out_path.unlink(missing_ok=True)


def run_pandoc_convert(
    source: Path,
    target: Path,
    *,
    extra_args: list[str] | None = None,
    timeout_seconds: float | None = None,
) -> None:
    require_pandoc()
    target.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "pandoc",
        "-f",
        "markdown+raw_tex",
        str(source),
        "-o",
        str(target),
        "--standalone",
        *(extra_args or []),
    ]
    kwargs: dict[str, float] = {}
    if timeout_seconds is not None:
        kwargs["timeout_seconds"] = timeout_seconds
    run_checked(cmd, label=f"pandoc export for {source.name}", **kwargs)
