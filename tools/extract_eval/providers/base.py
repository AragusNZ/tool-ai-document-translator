from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from document_translator.config.settings import PipelineConfig
from document_translator.extract.backends.protocol import ExtractBackend


@dataclass(frozen=True)
class BenchmarkRow:
    file: str
    backend: str
    chars: int | None = None
    pages: int | None = None
    elapsed_ms: float | None = None
    conversion_method: str | None = None
    error: str | None = None


class ExtractProvider(Protocol):
    name: str
    backend: ExtractBackend

    def extract(self, path: Path, *, config: PipelineConfig) -> BenchmarkRow: ...
