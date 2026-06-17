from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from document_translator.config.settings import PipelineConfig
from document_translator.errors import IssueCode
from document_translator.extract.common import ExtractionResult, persist_extraction_sidecars
from document_translator.lib.llm import MockLLMClient
from document_translator.models import TranslationOptions
from document_translator.pipeline import DocumentTranslationService
from document_translator.storage.paths import JobPaths
from document_translator.config.formats import ExportFormat


def test_persist_extraction_sidecars_writes_layout_and_screenshots(tmp_path: Path) -> None:
    paths = JobPaths(tmp_path / "runs", "job-sidecar", export_format=ExportFormat.PDF)
    paths.ensure_dirs()
    temp_dir = tmp_path / "shots-temp"
    temp_dir.mkdir()
    shot = temp_dir / "page-0001.png"
    shot.write_bytes(b"png")
    extraction = ExtractionResult(
        text="body\n",
        layout_json={"pages": [{"page_num": 1, "text_items": []}]},
        screenshot_paths=(shot,),
        screenshot_temp_dir=temp_dir,
    )

    persist_extraction_sidecars(paths, extraction)

    assert paths.extraction_layout_json.exists()
    assert (paths.screenshots_dir / "page-0001.png").exists()
    assert not temp_dir.exists()


def test_pipeline_warns_when_pymupdf_ignores_liteparse_flags(minimal_pdf: Path, tmp_path: Path) -> None:
    config = PipelineConfig(
        runs_dir=tmp_path / "runs",
        root=tmp_path,
        keep_work_files=True,
        target_pages="1",
        extract_screenshots=True,
    )
    expected = ExtractionResult(
        text="pdf text\n",
        pages=1,
        bytes=100,
        conversion_method="pymupdf",
        extract_backend="pymupdf",
    )
    with (
        patch("document_translator.pipeline.extract_single_file", return_value=expected),
        patch("document_translator.pipeline.export_markdown"),
    ):
        service = DocumentTranslationService(config=config, llm=MockLLMClient(prefix="[EN] "))
        result = service.translate(
            minimal_pdf,
            TranslationOptions(job_id="pymupdf-flags", no_translate=True),
        )

    ignored = [i for i in result.metadata.issues if i.code == IssueCode.EXTRACT_OPTION_IGNORED]
    assert len(ignored) >= 2


def test_pipeline_persists_layout_sidecar_with_keep_work_files(minimal_pdf: Path, tmp_path: Path) -> None:
    config = PipelineConfig(
        runs_dir=tmp_path / "runs",
        root=tmp_path,
        keep_work_files=True,
        extract_backend="liteparse",
    )
    expected = ExtractionResult(
        text="liteparse body\n",
        pages=1,
        bytes=100,
        conversion_method="liteparse",
        extract_backend="liteparse",
        layout_json={"pages": [{"page_num": 1, "text_items": [{"text": "hi"}]}]},
        extract_page_stats=({"page_num": 1, "char_count": 4, "ocr": False, "method": "liteparse"},),
    )
    with (
        patch("document_translator.pipeline.extract_single_file", return_value=expected),
        patch("document_translator.pipeline.export_markdown"),
    ):
        service = DocumentTranslationService(config=config, llm=MockLLMClient(prefix="[EN] "))
        result = service.translate(
            minimal_pdf,
            TranslationOptions(job_id="layout-sidecar", no_translate=True),
        )

    layout_path = tmp_path / "runs" / "layout-sidecar" / "artifacts" / "01-extraction-layout.json"
    assert layout_path.exists()
    assert result.metadata.extract_backend == "liteparse"
    assert result.metadata.extract_page_stats[0]["page_num"] == 1
    assert result.metadata.artifact_availability["extraction_layout_json"] is True
