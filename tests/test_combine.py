from __future__ import annotations

from pathlib import Path

from document_translator.config.formats import ExportFormat
from document_translator.export.combine import build_export_markdown


def test_build_export_markdown_pdf_wraps_cover(tmp_path: Path) -> None:
    body = tmp_path / "body.md"
    body.write_text("# Body\n\nTranslated text.\n", encoding="utf-8")
    combined = build_export_markdown("# Cover\n\nSummary.", body, ExportFormat.PDF)
    assert '<div class="cover-page">' in combined
    assert "\\newpage" not in combined
    assert "# Body" in combined


def test_build_export_markdown_docx_uses_newpage(tmp_path: Path) -> None:
    body = tmp_path / "body.md"
    body.write_text("# Body\n\nTranslated text.\n", encoding="utf-8")
    combined = build_export_markdown("# Cover\n\nSummary.", body, ExportFormat.DOCX)
    assert '<div class="cover-page">' not in combined
    assert "\\newpage" in combined
    assert "# Body" in combined


def test_build_export_markdown_txt_uses_separator(tmp_path: Path) -> None:
    body = tmp_path / "body.md"
    body.write_text("Body text.\n", encoding="utf-8")
    combined = build_export_markdown("Cover line.", body, ExportFormat.TXT)
    assert combined.startswith("Cover line.")
    assert "\n\n---\n\n" in combined
    assert "Body text." in combined


def test_build_export_markdown_md_uses_separator(tmp_path: Path) -> None:
    body = tmp_path / "body.md"
    body.write_text("Body text.\n", encoding="utf-8")
    combined = build_export_markdown("Cover line.", body, ExportFormat.MD)
    assert "\n\n---\n\n" in combined
