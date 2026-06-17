from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from document_translator.lib.subprocess.run import run_checked


def require_libreoffice() -> None:
    if shutil.which("libreoffice") is None:
        raise RuntimeError("libreoffice not found on PATH for document conversion")


def convert_file(
    input_path: Path,
    *,
    output_format: str,
    out_dir: str | Path,
    timeout_seconds: float | None = None,
) -> Path:
    require_libreoffice()
    cmd = [
        "libreoffice",
        "--headless",
        "--convert-to",
        output_format,
        "--outdir",
        str(out_dir),
        str(input_path),
    ]
    kwargs: dict[str, float] = {}
    if timeout_seconds is not None:
        kwargs["timeout_seconds"] = timeout_seconds
    run_checked(cmd, label="libreoffice conversion", **kwargs)
    converted = Path(out_dir) / f"{input_path.stem}.{output_format}"
    if not converted.exists():
        raise RuntimeError(f"libreoffice did not produce expected output: {converted.name}")
    return converted


def convert_doc_to_docx(doc_path: Path, *, timeout_seconds: float | None = None) -> Path:
    with tempfile.TemporaryDirectory() as tmp_dir:
        converted = convert_file(
            doc_path,
            output_format="docx",
            out_dir=tmp_dir,
            timeout_seconds=timeout_seconds,
        )
        persistent = doc_path.parent / f".{doc_path.stem}.converted.docx"
        shutil.copy2(converted, persistent, follow_symlinks=False)
        return persistent


def convert_docx_to_doc(
    docx_path: Path,
    target: Path,
    *,
    timeout_seconds: float | None = None,
) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp_dir:
        converted = convert_file(
            docx_path,
            output_format="doc",
            out_dir=tmp_dir,
            timeout_seconds=timeout_seconds,
        )
        shutil.move(str(converted), str(target))
