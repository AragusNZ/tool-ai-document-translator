from __future__ import annotations

import shutil


def tesseract_available() -> bool:
    if shutil.which("tesseract") is None:
        return False
    try:
        import pymupdf

        pymupdf.get_tessdata()
        return True
    except Exception:
        return shutil.which("tesseract") is not None


def require_tesseract() -> None:
    if not tesseract_available():
        raise RuntimeError(
            "tesseract not found on PATH. Install with: sudo apt install tesseract-ocr"
        )
