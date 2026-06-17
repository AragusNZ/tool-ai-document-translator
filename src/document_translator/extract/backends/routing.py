from __future__ import annotations

from typing import Literal

from document_translator.config.formats import LITEPARSE_INPUT_SUFFIXES
from document_translator.config.settings import PipelineConfig
from document_translator.extract.backends.liteparse import LiteParseBackend
from document_translator.extract.backends.protocol import ExtractBackend
from document_translator.extract.backends.pymupdf import PyMuPDFBackend

ExtractBackendName = Literal["pymupdf", "liteparse"]

LITEPARSE_SUFFIXES = LITEPARSE_INPUT_SUFFIXES

BACKEND_ROUTED_SUFFIXES: frozenset[str] = frozenset({".pdf"}) | LITEPARSE_SUFFIXES

_PYMUPDF = PyMuPDFBackend()
_LITEPARSE = LiteParseBackend()


def uses_backend_routing(suffix: str) -> bool:
    return suffix.lower() in BACKEND_ROUTED_SUFFIXES


def resolve_backend_name(suffix: str, config: PipelineConfig) -> ExtractBackendName:
    normalized = suffix.lower()
    requested = config.extract_backend

    if requested == "pymupdf":
        if normalized in LITEPARSE_SUFFIXES:
            raise RuntimeError(
                f"PyMuPDF backend does not support {normalized} files; "
                "use --extract-backend liteparse or auto"
            )
        return "pymupdf"

    if requested == "liteparse":
        return "liteparse"

    # auto
    if normalized == ".pdf":
        return "pymupdf"
    if normalized in LITEPARSE_SUFFIXES:
        return "liteparse"
    raise RuntimeError(f"No extract backend configured for {normalized} files")


def get_backend(name: ExtractBackendName) -> ExtractBackend:
    if name == "pymupdf":
        return _PYMUPDF
    return _LITEPARSE
