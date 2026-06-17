from __future__ import annotations

from pathlib import Path
from typing import Protocol

from document_translator.config.settings import PipelineConfig


class ExtractBackend(Protocol):
    name: str

    def extract(self, path: Path, *, config: PipelineConfig): ...
