from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from document_translator.config.settings import PipelineConfig
from document_translator.lib.llm.mock import MockLLMClient
from document_translator.models import TranslationOptions
from document_translator.pipeline import DocumentTranslationService
from document_translator.storage.checkpoint import (
    CheckpointStage,
    CheckpointState,
    source_text_hash,
    write_checkpoint,
    write_chunk_checkpoint,
)
from document_translator.types import JobStatus, TranslationMode


@pytest.mark.integration
def test_resume_skips_completed_translation_chunks(spanish_contract: Path, tmp_path: Path) -> None:
    config = PipelineConfig(runs_dir=tmp_path / "runs", root=tmp_path, chunk_size=120)
    job_id = "resume-job"
    body_text = spanish_contract.read_text(encoding="utf-8")
    body_hash = source_text_hash(body_text)

    failing = MockLLMClient(prefix="[EN] ")
    base_complete = failing.complete

    def fail_on_second_chunk(system: str, user: str) -> str:
        if "Chunk 2" in user:
            raise RuntimeError("simulated chunk failure")
        return base_complete(system, user)

    failing.complete = fail_on_second_chunk  # type: ignore[method-assign]

    service = DocumentTranslationService(config=config, llm=failing)
    with patch("document_translator.pipeline.export_markdown"):
        first = service.translate(
            spanish_contract,
            TranslationOptions(job_id=job_id, target_lang="en", translation_mode=TranslationMode.QUICK),
        )
    assert first.status == JobStatus.FAILED

    resume_mock = MockLLMClient(prefix="[EN] ")
    service = DocumentTranslationService(config=config, llm=resume_mock)
    with patch("document_translator.pipeline.export_markdown"):
        second = service.translate(
            spanish_contract,
            TranslationOptions(
                job_id=job_id,
                target_lang="en",
                translation_mode=TranslationMode.QUICK,
                resume=True,
            ),
        )

    assert second.status == JobStatus.COMPLETED
    assert second.metadata.resumed_from_checkpoint is True
    resumed_calls = [user for _system, user in resume_mock.calls if "Chunk" in user]
    assert resumed_calls
    assert all("Chunk 1" not in user for user in resumed_calls)


def test_manual_checkpoint_resume_uses_cached_chunk(tmp_path: Path) -> None:
    config = PipelineConfig(runs_dir=tmp_path / "runs", root=tmp_path, chunk_size=80)
    job_id = "manual-resume"
    job_root = tmp_path / "runs" / job_id
    artifacts = job_root / "artifacts"
    artifacts.mkdir(parents=True)
    body = (
        "Paragraph one has enough words to occupy the first chunk by itself.\n\n"
        "Paragraph two also has enough words to force a second translation chunk."
    )
    extracted = f"---\nsource: sample.txt\n---\n\n{body}"
    (artifacts / "01-extracted.md").write_text(extracted, encoding="utf-8")
    body_hash = source_text_hash(body)
    write_checkpoint(
        artifacts / "checkpoint.json",
        CheckpointState(
            stage=CheckpointStage.TRANSLATING_PASS1,
            chunk_index=0,
            pass_num=1,
            source_hash=body_hash,
            llm=config.llm,
            translation_mode="quick",
            chunk_count=2,
            target_lang="en",
        ),
    )
    write_chunk_checkpoint(
        artifacts / "checkpoints",
        pass_num=1,
        chunk_index=0,
        text="[cached] Paragraph one.",
        source_hash=body_hash,
        llm=config.llm,
    )

    sample = tmp_path / "sample.txt"
    sample.write_text(body, encoding="utf-8")
    mock = MockLLMClient(prefix="[EN] ")
    service = DocumentTranslationService(config=config, llm=mock)
    with patch("document_translator.pipeline.export_markdown"):
        result = service.translate(
            sample,
            TranslationOptions(job_id=job_id, target_lang="en", source_lang="es", resume=True),
        )

    assert result.status in {JobStatus.COMPLETED, JobStatus.COMPLETED_WITH_WARNINGS}
    chunk_calls = [user for _system, user in mock.calls if "Chunk" in user]
    assert len(chunk_calls) == 1
    assert "Chunk 2" in chunk_calls[0]
    assert "Chunk 1" not in chunk_calls[0]
