"""Extract DOCX to markdown via mammoth."""
from __future__ import annotations

from pathlib import Path


def extract_docx(path: Path) -> tuple[str, list[str]]:
    import mammoth
    from markdownify import markdownify

    with path.open("rb") as f:
        result = mammoth.convert_to_html(f)
    warnings = [str(m) for m in result.messages]
    html = result.value
    md = markdownify(html, heading_style="ATX", bullets="-")
    return md.strip() + "\n", warnings
