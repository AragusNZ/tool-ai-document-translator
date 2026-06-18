"""Extract HTML to markdown via pandoc or markdownify fallback."""

from __future__ import annotations

from pathlib import Path

from document_translator.lib.subprocess.pandoc import run_pandoc_to_markdown


def extract_html(path: Path, *, timeout_seconds: float | None = None) -> tuple[str, list[str], str]:
    try:
        return run_pandoc_to_markdown(path, timeout_seconds=timeout_seconds), [], "pandoc"
    except RuntimeError:
        from markdownify import markdownify

        raw = path.read_text(encoding="utf-8", errors="replace")
        md = markdownify(raw, heading_style="ATX", bullets="-").strip() + "\n"
        return md, ["pandoc unavailable; used markdownify HTML fallback"], "markdownify"
