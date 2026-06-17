from __future__ import annotations

import shutil
from pathlib import Path

from document_translator.lib.subprocess.run import run_checked


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


def convert_markdown_to_pdf(
    source: Path,
    target: Path,
    *,
    css_path: Path | None = None,
    timeout_seconds: float | None = None,
) -> None:
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
    kwargs: dict[str, float] = {}
    if timeout_seconds is not None:
        kwargs["timeout_seconds"] = timeout_seconds
    run_checked(cmd, label=f"pandoc PDF export for {source.name}", **kwargs)
