from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from document_translator.cli import main
from document_translator.config.settings import PipelineConfig
from document_translator.errors import IssueCode
from document_translator.lib.llm.mock import MockLLMClient
from document_translator.models import TranslationOptions
from document_translator.pipeline import DocumentTranslationService
from document_translator.types import JobStatus, TranslationMode


def test_translation_options_normalizes_source_lang() -> None:
    opts = TranslationOptions(source_lang="ES")
    assert opts.source_lang == "es"


def test_cli_invalid_source_lang(tmp_path: Path) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")
    code = main(
        [
            "translate",
            str(doc),
            "--job-id",
            "bad-source-lang",
            "--output-dir",
            str(tmp_path / "runs"),
            "--source-lang",
            "spanish",
        ]
    )
    assert code == 1


@pytest.mark.integration
def test_source_lang_override_used(spanish_contract: Path, tmp_path: Path) -> None:
    config = PipelineConfig(runs_dir=tmp_path / "runs", root=tmp_path, chunk_size=500)
    service = DocumentTranslationService(config=config, llm=MockLLMClient(prefix="[EN] "))

    with patch("document_translator.pipeline.export_markdown"):
        result = service.translate(
            spanish_contract,
            TranslationOptions(
                job_id="source-override",
                source_lang="es",
                target_lang="en",
                translation_mode=TranslationMode.QUICK,
            ),
        )

    assert result.status == JobStatus.COMPLETED
    assert result.metadata.source_lang == "es"
    assert result.metadata.source_lang_override is True
    assert result.metadata.source_lang_confidence == 1.0
    assert not any(issue.code == IssueCode.SOURCE_LANG_MISMATCH for issue in result.metadata.issues)


@pytest.mark.integration
def test_source_lang_override_mismatch_warns(spanish_contract: Path, tmp_path: Path) -> None:
    config = PipelineConfig(runs_dir=tmp_path / "runs", root=tmp_path, chunk_size=500)
    service = DocumentTranslationService(config=config, llm=MockLLMClient(prefix="[EN] "))

    with patch("document_translator.pipeline.export_markdown"):
        result = service.translate(
            spanish_contract,
            TranslationOptions(
                job_id="source-mismatch",
                source_lang="de",
                target_lang="en",
                translation_mode=TranslationMode.QUICK,
            ),
        )

    assert result.status in (JobStatus.COMPLETED, JobStatus.COMPLETED_WITH_WARNINGS)
    assert result.metadata.source_lang_override is True
    mismatch = [i for i in result.metadata.issues if i.code == IssueCode.SOURCE_LANG_MISMATCH]
    assert len(mismatch) == 1
    assert mismatch[0].scope.get("detected") == "es"
    assert mismatch[0].scope.get("override") == "de"
