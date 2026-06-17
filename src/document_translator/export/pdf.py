from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def default_css_path() -> Path:
    return Path(__file__).resolve().parent / "translation.css"


def _ensure_weasyprint() -> None:
    try:
        import weasyprint  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "weasyprint is not installed. Install with: pip install weasyprint "
            "(and system libs: libpango, etc.)"
        ) from exc


def convert_markdown_to_pdf(source: Path, target: Path, *, css_path: Path | None = None) -> None:
    if shutil.which("pandoc") is None:
        raise RuntimeError("pandoc not found on PATH. Install with: sudo apt install pandoc")

    _ensure_weasyprint()
    css = css_path or default_css_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "pandoc",
        str(source),
        "-o",
        str(target),
        "--pdf-engine=weasyprint",
        "--css",
        str(css),
        "--standalone",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "unknown error").strip()
        raise RuntimeError(f"pandoc failed for {source.name}: {detail}")
