from __future__ import annotations

from enum import Enum
from pathlib import Path

# Office and image inputs routed to LiteParse in auto mode (requires [extract-liteparse]).
LITEPARSE_OFFICE_SUFFIXES: frozenset[str] = frozenset({".pptx", ".ppt", ".xlsx", ".xls"})
LITEPARSE_IMAGE_SUFFIXES: frozenset[str] = frozenset({".png", ".jpg", ".jpeg", ".tiff", ".webp"})
LITEPARSE_INPUT_SUFFIXES: frozenset[str] = LITEPARSE_OFFICE_SUFFIXES | LITEPARSE_IMAGE_SUFFIXES

INPUT_SUFFIX_TO_EXPORT: dict[str, str] = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".doc": "doc",
    ".odt": "odt",
    ".rtf": "rtf",
    ".txt": "txt",
    ".md": "md",
    ".markdown": "md",
    ".epub": "epub",
    ".html": "html",
    ".htm": "html",
    ".pptx": "pdf",
    ".ppt": "pdf",
    ".xlsx": "pdf",
    ".xls": "pdf",
    ".png": "pdf",
    ".jpg": "pdf",
    ".jpeg": "pdf",
    ".tiff": "pdf",
    ".webp": "pdf",
}

SUPPORTED_INPUT_SUFFIXES: frozenset[str] = frozenset(INPUT_SUFFIX_TO_EXPORT)
SUPPORTED_EXTENSIONS = SUPPORTED_INPUT_SUFFIXES


class ExportFormat(str, Enum):
    PDF = "pdf"
    DOCX = "docx"
    DOC = "doc"
    ODT = "odt"
    RTF = "rtf"
    TXT = "txt"
    MD = "md"
    EPUB = "epub"
    HTML = "html"


def resolve_export_format(*, input_path: Path, requested: ExportFormat | None) -> ExportFormat:
    if requested is not None:
        return requested
    suffix = input_path.suffix.lower()
    mapped = INPUT_SUFFIX_TO_EXPORT.get(suffix)
    if mapped is None:
        return ExportFormat.PDF
    return ExportFormat(mapped)
