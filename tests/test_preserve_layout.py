from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from document_translator.config.settings import PipelineConfig
from document_translator.errors import IssueCode
from document_translator.extract.common import ExtractionResult, translation_body_text
from document_translator.lib.llm import MockLLMClient
from document_translator.models import TranslationOptions
from document_translator.pipeline import DocumentTranslationService
from document_translator.storage.checkpoint import (
    CheckpointStage,
    CheckpointState,
    source_text_hash,
    write_checkpoint,
)
from document_translator.types import JobStatus


def test_translation_body_text_prefers_layout() -> None:
    result = ExtractionResult(text="flat body\n", layout_text="layout body\n")
    assert translation_body_text(result, preserve_layout=True) == "layout body\n"
    assert translation_body_text(result, preserve_layout=False) == "flat body\n"


@pytest.mark.integration
def test_preserve_layout_uses_layout_text_in_translation(tmp_path: Path) -> None:
    source = tmp_path / "doc.txt"
    source.write_text("texto plano", encoding="utf-8")
    config = PipelineConfig(
        runs_dir=tmp_path / "runs",
        root=tmp_path,
        preserve_layout=True,
        chunk_size=500,
    )
    mock = MockLLMClient(prefix="[EN] ")
    service = DocumentTranslationService(config=config, llm=mock)

    expected = ExtractionResult(
        text="flat text only\n",
        layout_text="layout preserved text\n",
        pages=1,
        bytes=20,
        conversion_method="liteparse",
        extract_backend="liteparse",
    )

    with (
        patch("document_translator.pipeline.extract_single_file", return_value=expected),
        patch("document_translator.pipeline.export_markdown"),
    ):
        result = service.translate(
            source,
            TranslationOptions(
                job_id="layout-job",
                target_lang="en",
                source_lang="es",
            ),
        )

    assert result.metadata.used_layout_text is True
    translation_calls = [user for _system, user in mock.calls if "Chunk" in user]
    assert translation_calls
    assert "layout preserved text" in translation_calls[0]


@pytest.mark.integration
def test_preserve_layout_warns_when_unavailable(minimal_pdf: Path, tmp_path: Path) -> None:
    config = PipelineConfig(runs_dir=tmp_path / "runs", root=tmp_path, preserve_layout=True)
    mock = MockLLMClient(prefix="[EN] ")
    service = DocumentTranslationService(config=config, llm=mock)

    with patch("document_translator.pipeline.export_markdown"):
        result = service.translate(
            minimal_pdf,
            TranslationOptions(job_id="layout-warn", target_lang="en"),
        )

    codes = {issue.code for issue in result.metadata.issues}
    assert IssueCode.PRESERVE_LAYOUT_UNAVAILABLE in codes or IssueCode.EXTRACT_OPTION_IGNORED in codes


def test_preserve_layout_resume_restores_layout_body_checkpoint(tmp_path: Path) -> None:
    config = PipelineConfig(
        runs_dir=tmp_path / "runs",
        root=tmp_path,
        preserve_layout=True,
        chunk_size=80,
    )
    job_id = "layout-resume"
    job_root = tmp_path / "runs" / job_id
    artifacts = job_root / "artifacts"
    artifacts.mkdir(parents=True)
    flat_body = "flat extracted body for display only\n"
    layout_body = "layout preserved translation source\n"
    extracted = f"---\nsource: sample.pdf\n---\n\n{flat_body}"
    (artifacts / "01-extracted.md").write_text(extracted, encoding="utf-8")
    extract_dir = artifacts / "checkpoints" / "extract"
    extract_dir.mkdir(parents=True)
    (extract_dir / "layout-body.md").write_text(layout_body, encoding="utf-8")
    body_hash = source_text_hash(layout_body)
    write_checkpoint(
        artifacts / "checkpoint.json",
        CheckpointState(
            stage=CheckpointStage.TRANSLATING_PASS1,
            chunk_index=0,
            pass_num=1,
            source_hash=body_hash,
            llm=config.llm,
            translation_mode="quick",
            chunk_count=1,
            target_lang="en",
        ),
    )

    sample = tmp_path / "sample.pdf"
    sample.write_bytes(b"%PDF-1.4 minimal")
    mock = MockLLMClient(prefix="[EN] ")
    service = DocumentTranslationService(config=config, llm=mock)
    with patch("document_translator.pipeline.export_markdown"):
        result = service.translate(
            sample,
            TranslationOptions(job_id=job_id, target_lang="en", source_lang="es", resume=True),
        )

    assert result.status in {JobStatus.COMPLETED, JobStatus.COMPLETED_WITH_WARNINGS}
    assert result.metadata.used_layout_text is True
    assert result.metadata.resumed_from_checkpoint is True
    translation_calls = [user for _system, user in mock.calls if "Chunk" in user]
    assert translation_calls
    assert "layout preserved translation source" in translation_calls[0]
    assert "flat extracted body" not in translation_calls[0]
