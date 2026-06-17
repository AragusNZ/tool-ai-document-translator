from __future__ import annotations

import time
from pathlib import Path

from document_translator.config.settings import PipelineConfig
from document_translator.extract.backends.liteparse import LiteParseBackend

from tools.extract_eval.providers.base import BenchmarkRow


class LiteParseProvider:
    name = "liteparse"

    def __init__(self) -> None:
        self.backend = LiteParseBackend()

    def extract(self, path: Path, *, config: PipelineConfig) -> BenchmarkRow:
        started = time.perf_counter()
        try:
            result = self.backend.extract(path, config=config)
        except Exception as exc:
            return BenchmarkRow(file=path.name, backend=self.name, error=str(exc))
        elapsed_ms = (time.perf_counter() - started) * 1000
        return BenchmarkRow(
            file=path.name,
            backend=self.name,
            chars=len(result.text),
            pages=result.pages,
            elapsed_ms=round(elapsed_ms, 1),
            conversion_method=result.conversion_method,
        )
