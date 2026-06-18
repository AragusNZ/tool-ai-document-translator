from __future__ import annotations

import os
from pathlib import Path

from tools.extract_eval.golden import (
    FIXTURES_DIR,
    GoldenCase,
    extract_for_golden,
    normalized_text_hash,
    write_manifest_cases,
)
from tools.extract_eval.golden import MANIFEST_PATH as GOLDEN_MANIFEST_PATH


def update_manifest_hashes(cases: list[GoldenCase]) -> list[GoldenCase]:
    updated: list[GoldenCase] = []
    for case in cases:
        path = FIXTURES_DIR / case.file
        text = extract_for_golden(case, path)
        updated.append(
            GoldenCase(
                file=case.file,
                backend=case.backend,
                pdf_ocr=case.pdf_ocr,
                min_chars=case.min_chars,
                normalized_text_sha256=normalized_text_hash(text),
                requires_liteparse=case.requires_liteparse,
            )
        )
    return updated


def write_manifest(cases: list[GoldenCase], path: Path = GOLDEN_MANIFEST_PATH) -> None:
    write_manifest_cases(cases, path=path)


def should_update_golden() -> bool:
    return os.environ.get("UPDATE_GOLDEN", "").lower() in {"1", "true", "yes"}
