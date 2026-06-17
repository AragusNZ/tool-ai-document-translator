from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from document_translator.config.settings import PipelineConfig
from document_translator.lib.llm.mock import MockLLMClient
from document_translator.models import TranslationOptions
from document_translator.pipeline import DocumentTranslationService
from document_translator.types import JobStatus, TranslationMode


def test_translation_options_normalizes_context() -> None:
    opts = TranslationOptions(translation_context="  Contract between A and B.  ")
    assert opts.translation_context == "Contract between A and B."


@pytest.mark.integration
def test_translation_context_in_metadata(spanish_contract: Path, tmp_path: Path) -> None:
    config = PipelineConfig(runs_dir=tmp_path / "runs", root=tmp_path, chunk_size=500)
    mock = MockLLMClient(prefix="[EN] ")
    service = DocumentTranslationService(config=config, llm=mock)
    context = "This is a contract between Acme Corp and Beta LLC."

    with patch("document_translator.pipeline.export_markdown"):
        result = service.translate(
            spanish_contract,
            TranslationOptions(
                job_id="ctx-job",
                target_lang="en",
                translation_mode=TranslationMode.QUICK,
                translation_context=context,
            ),
        )

    assert result.status == JobStatus.COMPLETED
    assert result.metadata.translation_context == context
    translation_calls = [user for _system, user in mock.calls if "Chunk" in user]
    assert translation_calls
    assert all("Translation context:" in user and context in user for user in translation_calls)
