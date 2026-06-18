from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from document_translator.config.settings import PipelineConfig
from document_translator.extract.backends.liteparse import LiteParseBackend
from document_translator.extract.backends.pymupdf import PyMuPDFBackend
from document_translator.extract.common import normalize_text

_REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = _REPO_ROOT / "tests" / "fixtures" / "extract"
MANIFEST_PATH = FIXTURES_DIR / "golden_manifest.json"


@dataclass(frozen=True)
class GoldenCase:
    file: str
    backend: str
    pdf_ocr: bool
    min_chars: int
    normalized_text_sha256: str
    requires_liteparse: bool = False


def normalized_text_hash(text: str) -> str:
    normalized = normalize_text(text).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def load_manifest(path: Path = MANIFEST_PATH) -> list[GoldenCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases: list[GoldenCase] = []
    for entry in payload["cases"]:
        cases.append(
            GoldenCase(
                file=str(entry["file"]),
                backend=str(entry["backend"]),
                pdf_ocr=bool(entry.get("pdf_ocr", False)),
                min_chars=int(entry.get("min_chars", 1)),
                normalized_text_sha256=str(entry["normalized_text_sha256"]),
                requires_liteparse=bool(entry.get("requires_liteparse", False)),
            )
        )
    return cases


def golden_index() -> dict[tuple[str, str], GoldenCase]:
    return {(case.file, case.backend): case for case in load_manifest()}


def write_manifest_cases(cases: list[GoldenCase], path: Path = MANIFEST_PATH) -> None:
    payload = {
        "version": 1,
        "cases": [
            {
                "file": case.file,
                "backend": case.backend,
                "pdf_ocr": case.pdf_ocr,
                "min_chars": case.min_chars,
                "normalized_text_sha256": case.normalized_text_sha256,
                **({"requires_liteparse": True} if case.requires_liteparse else {}),
            }
            for case in cases
        ],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def extract_for_golden(case: GoldenCase, path: Path) -> str:
    config = PipelineConfig(pdf_ocr=case.pdf_ocr, extract_backend=case.backend)  # type: ignore[arg-type]
    backend = LiteParseBackend() if case.backend == "liteparse" else PyMuPDFBackend()
    return backend.extract(path, config=config).text
