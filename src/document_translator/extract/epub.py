"""Extract EPUB to markdown via ebooklib + markdownify."""

from __future__ import annotations

from pathlib import Path


def extract_epub(path: Path) -> tuple[str, list[str]]:
    import ebooklib
    from ebooklib import epub
    from markdownify import markdownify

    book = epub.read_epub(str(path))
    chapters: list[str] = []
    warnings: list[str] = []

    for item in book.get_items():
        if item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue
        content = item.get_content().decode("utf-8", errors="replace")
        md = markdownify(content, heading_style="ATX", bullets="-").strip()
        if md:
            chapters.append(md)

    if not chapters:
        warnings.append("EPUB contained no document body items")
        return "\n", warnings

    return "\n\n".join(chapters).strip() + "\n", warnings
