"""Pluggable extract backends (pymupdf, liteparse)."""

from document_translator.extract.backends.protocol import ExtractBackend

__all__ = ["ExtractBackend"]
