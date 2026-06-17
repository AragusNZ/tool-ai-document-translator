from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


def require_pandoc() -> None:
    if shutil.which("pandoc") is None:
        raise RuntimeError("pandoc not found on PATH. Install with: sudo apt install pandoc")


def run_pandoc_to_markdown(input_path: Path) -> str:
    require_pandoc()

    with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as tmp:
        out_path = Path(tmp.name)

    try:
        cmd = ["pandoc", str(input_path), "-t", "markdown", "-o", str(out_path), "--wrap=none"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "unknown error").strip()
            raise RuntimeError(f"pandoc conversion failed: {detail}")
        return out_path.read_text(encoding="utf-8", errors="ignore").strip() + "\n"
    finally:
        out_path.unlink(missing_ok=True)


def run_pandoc_convert(
    source: Path,
    target: Path,
    *,
    extra_args: list[str] | None = None,
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
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "unknown error").strip()
        raise RuntimeError(f"pandoc failed for {source.name} -> {target.name}: {detail}")
