from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from document_translator.export.pdf import convert_markdown_to_pdf, default_css_path, resolve_pdf_css_path


def _pdf_export_available() -> bool:
    if shutil.which("pandoc") is None:
        return False
    try:
        import weasyprint  # noqa: F401
    except ImportError:
        return False
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "probe.md"
        target = Path(tmp) / "probe.pdf"
        source.write_text("# Probe\n\nTest.\n", encoding="utf-8")
        try:
            convert_markdown_to_pdf(source, target)
        except RuntimeError:
            return False
        return target.exists() and target.stat().st_size > 0


def test_default_css_path_exists() -> None:
    css = default_css_path()
    assert css.name == "translation.css"
    assert css.exists()
    assert resolve_pdf_css_path(rtl=True).name == "translation-rtl.css"


def test_convert_missing_pandoc(tmp_path: Path) -> None:
    source = tmp_path / "doc.md"
    source.write_text("# Title\n", encoding="utf-8")
    target = tmp_path / "out.pdf"
    with patch("document_translator.export.pdf.shutil.which", return_value=None):
        with pytest.raises(RuntimeError, match="pandoc not found"):
            convert_markdown_to_pdf(source, target)


def test_ensure_weasyprint_import_error() -> None:
    import builtins

    real_import = builtins.__import__

    def fake_import(name: str, *args, **kwargs):  # noqa: ANN001
        if name == "weasyprint":
            raise ImportError("no weasyprint")
        return real_import(name, *args, **kwargs)

    from document_translator.export import pdf as pdf_mod

    with patch("builtins.__import__", side_effect=fake_import):
        with pytest.raises(RuntimeError, match="weasyprint is not installed"):
            pdf_mod._ensure_weasyprint()


def test_convert_missing_weasyprint(tmp_path: Path) -> None:
    source = tmp_path / "doc.md"
    source.write_text("# Title\n", encoding="utf-8")
    target = tmp_path / "out.pdf"
    with patch("document_translator.export.pdf.shutil.which", return_value="/usr/bin/pandoc"):
        with patch(
            "document_translator.export.pdf._ensure_weasyprint",
            side_effect=RuntimeError("weasyprint is not installed"),
        ):
            with pytest.raises(RuntimeError, match="weasyprint"):
                convert_markdown_to_pdf(source, target)


def test_convert_pandoc_failure(tmp_path: Path) -> None:
    source = tmp_path / "doc.md"
    source.write_text("# Title\n\nBody.\n", encoding="utf-8")
    target = tmp_path / "out.pdf"
    with patch("document_translator.export.pdf.shutil.which", return_value="/usr/bin/pandoc"):
        with patch("document_translator.export.pdf._ensure_weasyprint"):
            with patch(
                "document_translator.lib.subprocess.run.subprocess.run",
                return_value=subprocess.CompletedProcess([], 1, stderr="engine failed"),
            ):
                with pytest.raises(RuntimeError, match="pandoc PDF export for doc.md failed"):
                    convert_markdown_to_pdf(source, target)


def test_convert_success_mocked(tmp_path: Path) -> None:
    source = tmp_path / "doc.md"
    source.write_text("# Title\n\nBody.\n", encoding="utf-8")
    target = tmp_path / "out.pdf"
    custom_css = tmp_path / "custom.css"
    custom_css.write_text("body { font-size: 12pt; }", encoding="utf-8")

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        out_path = Path(cmd[cmd.index("-o") + 1])
        out_path.write_bytes(b"%PDF-1.4 mock")
        assert "--pdf-engine=weasyprint" in cmd
        assert str(custom_css) in cmd
        return subprocess.CompletedProcess(cmd, 0)

    with patch("document_translator.export.pdf.shutil.which", return_value="/usr/bin/pandoc"):
        with patch("document_translator.export.pdf._ensure_weasyprint"):
            with patch("document_translator.lib.subprocess.run.subprocess.run", side_effect=fake_run):
                convert_markdown_to_pdf(source, target, css_path=custom_css)

    assert target.exists()
    assert target.read_bytes().startswith(b"%PDF")


def test_convert_uses_default_css_when_not_provided(tmp_path: Path) -> None:
    source = tmp_path / "doc.md"
    source.write_text("# Title\n", encoding="utf-8")
    target = tmp_path / "out.pdf"
    captured_cmd: list[str] = []

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured_cmd.extend(cmd)
        Path(cmd[cmd.index("-o") + 1]).write_bytes(b"%PDF mock")
        return subprocess.CompletedProcess(cmd, 0)

    with patch("document_translator.export.pdf.shutil.which", return_value="/usr/bin/pandoc"):
        with patch("document_translator.export.pdf._ensure_weasyprint"):
            with patch("document_translator.lib.subprocess.run.subprocess.run", side_effect=fake_run):
                convert_markdown_to_pdf(source, target)

    assert str(default_css_path()) in captured_cmd


@pytest.mark.requires_pandoc
@pytest.mark.requires_weasyprint
def test_pdf_export_integration(tmp_path: Path) -> None:
    if not _pdf_export_available():
        pytest.skip("pandoc/weasyprint export not available in this environment")

    source = tmp_path / "doc.md"
    source.write_text("# Title\n\nParagraph text.\n", encoding="utf-8")
    target = tmp_path / "out.pdf"
    convert_markdown_to_pdf(source, target)
    assert target.exists()
    assert target.stat().st_size > 0
