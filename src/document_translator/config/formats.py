from __future__ import annotations

from enum import Enum
from pathlib import Path

INPUT_SUFFIX_TO_EXPORT: dict[str, str] = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".doc": "doc",
    ".odt": "odt",
    ".rtf": "rtf",
    ".txt": "txt",
    ".md": "md",
    ".markdown": "md",
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


def resolve_export_format(*, input_path: Path, requested: ExportFormat | None) -> ExportFormat:
    if requested is not None:
        return requested
    suffix = input_path.suffix.lower()
    mapped = INPUT_SUFFIX_TO_EXPORT.get(suffix)
    if mapped is None:
        return ExportFormat.PDF
    return ExportFormat(mapped)
