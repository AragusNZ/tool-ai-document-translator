from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from document_translator import __version__
from document_translator.cli import _aggregate_exit_code, _exit_code_for_status, main
from document_translator.config.llms import supported_llms
from document_translator.config.settings import PipelineConfig
from document_translator.errors import ConfigurationError, IssueCode
from document_translator.lib.llm import MockLLMClient
from document_translator.models import ArtifactPaths, BatchJobResult, JobMetadata, JobResult
from document_translator.types import JobStatus, TranslationMode


def test_cli_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_exit_code_for_status_mapping() -> None:
    assert _exit_code_for_status(JobStatus.COMPLETED) == 0
    assert _exit_code_for_status(JobStatus.FAILED) == 2
    assert _exit_code_for_status(JobStatus.COMPLETED_WITH_WARNINGS) == 3


def test_cli_missing_input_file() -> None:
    code = main(["translate", "/nonexistent/document.txt", "--job-id", "missing-input"])
    assert code == 1


def test_cli_job_dir_exists_without_force_overwrite(tmp_path: Path) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")
    runs = tmp_path / "runs"
    job_dir = runs / "existing-job"
    job_dir.mkdir(parents=True)

    code = main(
        [
            "translate",
            str(doc),
            "--job-id",
            "existing-job",
            "--output-dir",
            str(runs),
        ]
    )
    assert code == 1


def test_cli_invalid_config_json(tmp_path: Path) -> None:
    bad_config = tmp_path / "bad.json"
    bad_config.write_text("{not json", encoding="utf-8")
    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")
    code = main(["translate", str(doc), "--config", str(bad_config), "--job-id", "cli-bad-config"])
    assert code == 1


def test_cli_json_success(tmp_path: Path) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")
    metadata = JobMetadata(job_id="cli-success", source_file="doc.txt")
    fake_result = JobResult(
        job_id="cli-success",
        status=JobStatus.COMPLETED,
        artifacts=ArtifactPaths(),
        metadata=metadata,
    )

    class FakeService:
        def __init__(self, config: PipelineConfig) -> None:
            self.config = config

        def translate(self, input_path: Path, options):  # noqa: ANN001
            return fake_result

    with patch("document_translator.cli.DocumentTranslationService", FakeService):
        code = main(
            [
                "translate",
                str(doc),
                "--job-id",
                "cli-success",
                "--output-dir",
                str(tmp_path / "runs"),
                "--format",
                "json",
            ]
        )

    assert code == 0


def test_cli_pipeline_failure_exit_2(tmp_path: Path) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")
    metadata = JobMetadata(job_id="cli-fail", source_file="doc.txt")
    fake_result = JobResult(
        job_id="cli-fail",
        status=JobStatus.FAILED,
        artifacts=ArtifactPaths(),
        metadata=metadata,
        error_message="pipeline broke",
        error_code=IssueCode.PIPELINE_FAILED,
    )

    class FakeService:
        def __init__(self, config: PipelineConfig) -> None:
            self.config = config

        def translate(self, input_path: Path, options):  # noqa: ANN001
            return fake_result

    with patch("document_translator.cli.DocumentTranslationService", FakeService):
        code = main(
            [
                "translate",
                str(doc),
                "--job-id",
                "cli-fail",
                "--output-dir",
                str(tmp_path / "runs"),
                "--format",
                "json",
            ]
        )

    assert code == 2


def test_cli_text_output_success(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")
    metadata = JobMetadata(
        job_id="text-out",
        source_file="doc.txt",
        artifact_availability={"final_output": True, "resolved_md": False, "metadata_json": True, "status_json": True},
    )
    fake_result = JobResult(
        job_id="text-out",
        status=JobStatus.COMPLETED,
        artifacts=ArtifactPaths(
            final_output=tmp_path / "out.txt",
            metadata_json=tmp_path / "metadata.json",
            status_json=tmp_path / "status.json",
        ),
        metadata=metadata,
    )

    class FakeService:
        def __init__(self, config: PipelineConfig) -> None:
            pass

        def translate(self, input_path: Path, options):  # noqa: ANN001
            return fake_result

    with patch("document_translator.cli.DocumentTranslationService", FakeService):
        code = main(
            [
                "translate",
                str(doc),
                "--job-id",
                "text-out",
                "--output-dir",
                str(tmp_path / "runs"),
                "--force-overwrite",
            ]
        )

    assert code == 0
    out = capsys.readouterr().out
    assert "text-out" in out
    assert "Final document:" in out


def test_cli_config_file_not_found(tmp_path: Path) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")
    code = main(["translate", str(doc), "--config", str(tmp_path / "missing.json"), "--job-id", "cfg-missing"])
    assert code == 1


def test_cli_output_dir_override(tmp_path: Path) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")
    custom_runs = tmp_path / "custom-runs"
    captured: dict[str, PipelineConfig] = {}

    class FakeService:
        def __init__(self, config: PipelineConfig) -> None:
            captured["config"] = config

        def translate(self, input_path: Path, options):  # noqa: ANN001
            metadata = JobMetadata(job_id="out-dir", source_file="doc.txt")
            return JobResult(
                job_id="out-dir",
                status=JobStatus.COMPLETED,
                artifacts=ArtifactPaths(),
                metadata=metadata,
            )

    with patch("document_translator.cli.DocumentTranslationService", FakeService):
        code = main(
            [
                "translate",
                str(doc),
                "--job-id",
                "out-dir",
                "--output-dir",
                str(custom_runs),
            ]
        )

    assert code == 0
    assert captured["config"].runs_dir == custom_runs


def test_cli_config_json_overrides(tmp_path: Path) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")
    custom_runs = tmp_path / "config-runs"
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({"chunk_size": 1200, "runs_dir": str(custom_runs)}),
        encoding="utf-8",
    )
    captured: dict[str, PipelineConfig] = {}

    class FakeService:
        def __init__(self, config: PipelineConfig) -> None:
            captured["config"] = config

        def translate(self, input_path: Path, options):  # noqa: ANN001
            metadata = JobMetadata(job_id="cfg-job", source_file="doc.txt")
            return JobResult(
                job_id="cfg-job",
                status=JobStatus.COMPLETED,
                artifacts=ArtifactPaths(),
                metadata=metadata,
            )

    with patch("document_translator.cli.DocumentTranslationService", FakeService):
        code = main(
            [
                "translate",
                str(doc),
                "--job-id",
                "cfg-job",
                "--config",
                str(config_file),
            ]
        )

    assert code == 0
    assert captured["config"].chunk_size == 1200
    assert captured["config"].runs_dir == custom_runs


def test_cli_export_format_flag(tmp_path: Path) -> None:
    doc = tmp_path / "doc.pdf"
    doc.write_bytes(b"%PDF-1.4")
    captured: dict[str, object] = {}

    class FakeService:
        def __init__(self, config: PipelineConfig) -> None:
            pass

        def translate(self, input_path: Path, options):  # noqa: ANN001
            captured["options"] = options
            metadata = JobMetadata(job_id="export-flag", source_file="doc.pdf")
            return JobResult(
                job_id="export-flag",
                status=JobStatus.COMPLETED,
                artifacts=ArtifactPaths(),
                metadata=metadata,
            )

    with patch("document_translator.cli.DocumentTranslationService", FakeService):
        code = main(
            [
                "translate",
                str(doc),
                "--job-id",
                "export-flag",
                "--output-dir",
                str(tmp_path / "runs"),
                "--export-format",
                "docx",
            ]
        )

    from document_translator.config.formats import ExportFormat

    assert code == 0
    assert captured["options"].export_format == ExportFormat.DOCX


def test_cli_export_format_from_config(tmp_path: Path) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"export_format": "odt"}), encoding="utf-8")
    captured: dict[str, object] = {}

    class FakeService:
        def __init__(self, config: PipelineConfig) -> None:
            pass

        def translate(self, input_path: Path, options):  # noqa: ANN001
            captured["options"] = options
            metadata = JobMetadata(job_id="export-cfg", source_file="doc.txt")
            return JobResult(
                job_id="export-cfg",
                status=JobStatus.COMPLETED,
                artifacts=ArtifactPaths(),
                metadata=metadata,
            )

    with patch("document_translator.cli.DocumentTranslationService", FakeService):
        code = main(
            [
                "translate",
                str(doc),
                "--job-id",
                "export-cfg",
                "--config",
                str(config_file),
            ]
        )

    from document_translator.config.formats import ExportFormat

    assert code == 0
    assert captured["options"].export_format == ExportFormat.ODT


def test_cli_target_lang_flag(tmp_path: Path) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")
    captured: dict[str, object] = {}

    class FakeService:
        def __init__(self, config: PipelineConfig) -> None:
            pass

        def translate(self, input_path: Path, options):  # noqa: ANN001
            captured["options"] = options
            metadata = JobMetadata(job_id="target-lang-flag", source_file="doc.txt")
            return JobResult(
                job_id="target-lang-flag",
                status=JobStatus.COMPLETED,
                artifacts=ArtifactPaths(),
                metadata=metadata,
            )

    with patch("document_translator.cli.DocumentTranslationService", FakeService):
        code = main(
            [
                "translate",
                str(doc),
                "--job-id",
                "target-lang-flag",
                "--output-dir",
                str(tmp_path / "runs"),
                "--target-lang",
                "es",
            ]
        )

    assert code == 0
    assert captured["options"].target_lang == "es"


def test_cli_target_lang_from_config(tmp_path: Path) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"target_lang": "de"}), encoding="utf-8")
    captured: dict[str, object] = {}

    class FakeService:
        def __init__(self, config: PipelineConfig) -> None:
            pass

        def translate(self, input_path: Path, options):  # noqa: ANN001
            captured["options"] = options
            metadata = JobMetadata(job_id="target-lang-cfg", source_file="doc.txt")
            return JobResult(
                job_id="target-lang-cfg",
                status=JobStatus.COMPLETED,
                artifacts=ArtifactPaths(),
                metadata=metadata,
            )

    with patch("document_translator.cli.DocumentTranslationService", FakeService):
        code = main(
            [
                "translate",
                str(doc),
                "--job-id",
                "target-lang-cfg",
                "--config",
                str(config_file),
            ]
        )

    assert code == 0
    assert captured["options"].target_lang == "de"


def test_cli_mode_defaults_to_quick(tmp_path: Path) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")
    captured: dict[str, object] = {}

    class FakeService:
        def __init__(self, config: PipelineConfig) -> None:
            pass

        def translate(self, input_path: Path, options):  # noqa: ANN001
            captured["options"] = options
            metadata = JobMetadata(job_id="mode-default", source_file="doc.txt")
            return JobResult(
                job_id="mode-default",
                status=JobStatus.COMPLETED,
                artifacts=ArtifactPaths(),
                metadata=metadata,
            )

    with patch("document_translator.cli.DocumentTranslationService", FakeService):
        code = main(
            [
                "translate",
                str(doc),
                "--job-id",
                "mode-default",
                "--output-dir",
                str(tmp_path / "runs"),
            ]
        )

    assert code == 0
    assert captured["options"].translation_mode == TranslationMode.QUICK


def test_cli_mode_flag(tmp_path: Path) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")
    captured: dict[str, object] = {}

    class FakeService:
        def __init__(self, config: PipelineConfig) -> None:
            pass

        def translate(self, input_path: Path, options):  # noqa: ANN001
            captured["options"] = options
            metadata = JobMetadata(job_id="mode-flag", source_file="doc.txt")
            return JobResult(
                job_id="mode-flag",
                status=JobStatus.COMPLETED,
                artifacts=ArtifactPaths(),
                metadata=metadata,
            )

    with patch("document_translator.cli.DocumentTranslationService", FakeService):
        code = main(
            [
                "translate",
                str(doc),
                "--job-id",
                "mode-flag",
                "--output-dir",
                str(tmp_path / "runs"),
                "--mode",
                "thorough",
            ]
        )

    assert code == 0
    assert captured["options"].translation_mode == TranslationMode.THOROUGH


def test_cli_no_translate_flag(tmp_path: Path) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")
    captured: dict[str, object] = {}

    class FakeService:
        def __init__(self, config: PipelineConfig) -> None:
            pass

        def translate(self, input_path: Path, options):  # noqa: ANN001
            captured["options"] = options
            metadata = JobMetadata(job_id="no-translate-flag", source_file="doc.txt")
            return JobResult(
                job_id="no-translate-flag",
                status=JobStatus.COMPLETED,
                artifacts=ArtifactPaths(),
                metadata=metadata,
            )

    with patch("document_translator.cli.DocumentTranslationService", FakeService):
        code = main(
            [
                "translate",
                str(doc),
                "--job-id",
                "no-translate-flag",
                "--output-dir",
                str(tmp_path / "runs"),
                "--no-translate",
            ]
        )

    assert code == 0
    assert captured["options"].no_translate is True


def test_cli_save_resolved_flag(tmp_path: Path) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")
    captured: dict[str, object] = {}

    class FakeService:
        def __init__(self, config: PipelineConfig) -> None:
            pass

        def translate(self, input_path: Path, options):  # noqa: ANN001
            captured["options"] = options
            metadata = JobMetadata(job_id="save-resolved-flag", source_file="doc.txt")
            return JobResult(
                job_id="save-resolved-flag",
                status=JobStatus.COMPLETED,
                artifacts=ArtifactPaths(),
                metadata=metadata,
            )

    with patch("document_translator.cli.DocumentTranslationService", FakeService):
        code = main(
            [
                "translate",
                str(doc),
                "--job-id",
                "save-resolved-flag",
                "--output-dir",
                str(tmp_path / "runs"),
                "--save-resolved",
            ]
        )

    assert code == 0
    assert captured["options"].save_resolved is True


def test_cli_no_cover_page_flag(tmp_path: Path) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")
    captured: dict[str, object] = {}

    class FakeService:
        def __init__(self, config: PipelineConfig) -> None:
            pass

        def translate(self, input_path: Path, options):  # noqa: ANN001
            captured["options"] = options
            metadata = JobMetadata(job_id="no-cover-flag", source_file="doc.txt")
            return JobResult(
                job_id="no-cover-flag",
                status=JobStatus.COMPLETED,
                artifacts=ArtifactPaths(),
                metadata=metadata,
            )

    with patch("document_translator.cli.DocumentTranslationService", FakeService):
        code = main(
            [
                "translate",
                str(doc),
                "--job-id",
                "no-cover-flag",
                "--output-dir",
                str(tmp_path / "runs"),
                "--no-cover-page",
            ]
        )

    assert code == 0
    assert captured["options"].no_cover_page is True


def test_cli_text_output_includes_resolved_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")
    resolved = tmp_path / "runs" / "resolved-out" / "artifacts" / "04-resolved.md"
    final = tmp_path / "runs" / "resolved-out" / "artifacts" / "05-final.pdf"

    class FakeService:
        def __init__(self, config: PipelineConfig) -> None:
            pass

        def translate(self, input_path: Path, options):  # noqa: ANN001
            metadata = JobMetadata(
                job_id="resolved-out",
                source_file="doc.txt",
                artifact_availability={
                    "final_output": True,
                    "resolved_md": True,
                    "metadata_json": True,
                    "status_json": True,
                },
            )
            return JobResult(
                job_id="resolved-out",
                status=JobStatus.COMPLETED,
                artifacts=ArtifactPaths(final_output=final, resolved_md=resolved),
                metadata=metadata,
            )

    with patch("document_translator.cli.DocumentTranslationService", FakeService):
        code = main(
            [
                "translate",
                str(doc),
                "--job-id",
                "resolved-out",
                "--output-dir",
                str(tmp_path / "runs"),
            ]
        )

    assert code == 0
    out = capsys.readouterr().out
    assert f"Final document: {final}" in out
    assert f"Resolved markdown: {resolved}" in out


def test_cli_no_translate_from_config(tmp_path: Path) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"no_translate": True}), encoding="utf-8")
    captured: dict[str, object] = {}

    class FakeService:
        def __init__(self, config: PipelineConfig) -> None:
            pass

        def translate(self, input_path: Path, options):  # noqa: ANN001
            captured["options"] = options
            metadata = JobMetadata(job_id="no-translate-cfg", source_file="doc.txt")
            return JobResult(
                job_id="no-translate-cfg",
                status=JobStatus.COMPLETED,
                artifacts=ArtifactPaths(),
                metadata=metadata,
            )

    with patch("document_translator.cli.DocumentTranslationService", FakeService):
        code = main(
            [
                "translate",
                str(doc),
                "--job-id",
                "no-translate-cfg",
                "--output-dir",
                str(tmp_path / "runs"),
                "--config",
                str(config_file),
            ]
        )

    assert code == 0
    assert captured["options"].no_translate is True


def test_cli_mode_from_config(tmp_path: Path) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"translation_mode": "thorough"}), encoding="utf-8")
    captured: dict[str, object] = {}

    class FakeService:
        def __init__(self, config: PipelineConfig) -> None:
            pass

        def translate(self, input_path: Path, options):  # noqa: ANN001
            captured["options"] = options
            metadata = JobMetadata(job_id="mode-cfg", source_file="doc.txt")
            return JobResult(
                job_id="mode-cfg",
                status=JobStatus.COMPLETED,
                artifacts=ArtifactPaths(),
                metadata=metadata,
            )

    with patch("document_translator.cli.DocumentTranslationService", FakeService):
        code = main(
            [
                "translate",
                str(doc),
                "--job-id",
                "mode-cfg",
                "--config",
                str(config_file),
            ]
        )

    assert code == 0
    assert captured["options"].translation_mode == TranslationMode.THOROUGH


def test_cli_mode_flag_overrides_config(tmp_path: Path) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"translation_mode": "thorough"}), encoding="utf-8")
    captured: dict[str, object] = {}

    class FakeService:
        def __init__(self, config: PipelineConfig) -> None:
            pass

        def translate(self, input_path: Path, options):  # noqa: ANN001
            captured["options"] = options
            metadata = JobMetadata(job_id="mode-override", source_file="doc.txt")
            return JobResult(
                job_id="mode-override",
                status=JobStatus.COMPLETED,
                artifacts=ArtifactPaths(),
                metadata=metadata,
            )

    with patch("document_translator.cli.DocumentTranslationService", FakeService):
        code = main(
            [
                "translate",
                str(doc),
                "--job-id",
                "mode-override",
                "--config",
                str(config_file),
                "--mode",
                "quick",
            ]
        )

    assert code == 0
    assert captured["options"].translation_mode == TranslationMode.QUICK


def test_cli_no_pdf_ocr_flag(tmp_path: Path) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")
    captured: dict[str, object] = {}

    class FakeService:
        def __init__(self, config: PipelineConfig) -> None:
            captured["config"] = config

        def translate(self, input_path: Path, options):  # noqa: ANN001
            metadata = JobMetadata(job_id="no-ocr-flag", source_file="doc.txt")
            return JobResult(
                job_id="no-ocr-flag",
                status=JobStatus.COMPLETED,
                artifacts=ArtifactPaths(),
                metadata=metadata,
            )

    with patch("document_translator.cli.DocumentTranslationService", FakeService):
        code = main(
            [
                "translate",
                str(doc),
                "--job-id",
                "no-ocr-flag",
                "--output-dir",
                str(tmp_path / "runs"),
                "--no-pdf-ocr",
            ]
        )

    assert code == 0
    assert captured["config"].pdf_ocr is False


def test_cli_no_pdf_ocr_flag_overrides_config(tmp_path: Path) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"pdf_ocr": True}), encoding="utf-8")
    captured: dict[str, object] = {}

    class FakeService:
        def __init__(self, config: PipelineConfig) -> None:
            captured["config"] = config

        def translate(self, input_path: Path, options):  # noqa: ANN001
            metadata = JobMetadata(job_id="no-ocr-override", source_file="doc.txt")
            return JobResult(
                job_id="no-ocr-override",
                status=JobStatus.COMPLETED,
                artifacts=ArtifactPaths(),
                metadata=metadata,
            )

    with patch("document_translator.cli.DocumentTranslationService", FakeService):
        code = main(
            [
                "translate",
                str(doc),
                "--job-id",
                "no-ocr-override",
                "--config",
                str(config_file),
                "--no-pdf-ocr",
            ]
        )

    assert code == 0
    assert captured["config"].pdf_ocr is False


def test_cli_pdf_ocr_from_config(tmp_path: Path) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"pdf_ocr": False}), encoding="utf-8")
    captured: dict[str, object] = {}

    class FakeService:
        def __init__(self, config: PipelineConfig) -> None:
            captured["config"] = config

        def translate(self, input_path: Path, options):  # noqa: ANN001
            metadata = JobMetadata(job_id="ocr-cfg", source_file="doc.txt")
            return JobResult(
                job_id="ocr-cfg",
                status=JobStatus.COMPLETED,
                artifacts=ArtifactPaths(),
                metadata=metadata,
            )

    with patch("document_translator.cli.DocumentTranslationService", FakeService):
        code = main(
            [
                "translate",
                str(doc),
                "--job-id",
                "ocr-cfg",
                "--config",
                str(config_file),
            ]
        )

    assert code == 0
    assert captured["config"].pdf_ocr is False


def test_cli_invalid_translation_mode_in_config(tmp_path: Path) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"translation_mode": "fast"}), encoding="utf-8")

    code = main(
        [
            "translate",
            str(doc),
            "--job-id",
            "mode-invalid",
            "--config",
            str(config_file),
        ]
    )

    assert code == 1


def test_cli_target_lang_flag_overrides_config(tmp_path: Path) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"target_lang": "de"}), encoding="utf-8")
    captured: dict[str, object] = {}

    class FakeService:
        def __init__(self, config: PipelineConfig) -> None:
            pass

        def translate(self, input_path: Path, options):  # noqa: ANN001
            captured["options"] = options
            metadata = JobMetadata(job_id="target-lang-override", source_file="doc.txt")
            return JobResult(
                job_id="target-lang-override",
                status=JobStatus.COMPLETED,
                artifacts=ArtifactPaths(),
                metadata=metadata,
            )

    with patch("document_translator.cli.DocumentTranslationService", FakeService):
        code = main(
            [
                "translate",
                str(doc),
                "--job-id",
                "target-lang-override",
                "--config",
                str(config_file),
                "--target-lang",
                "fr",
            ]
        )

    assert code == 0
    assert captured["options"].target_lang == "fr"


def test_cli_invalid_target_lang(tmp_path: Path) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")
    code = main(
        [
            "translate",
            str(doc),
            "--job-id",
            "bad-lang",
            "--output-dir",
            str(tmp_path / "runs"),
            "--target-lang",
            "english",
        ]
    )
    assert code == 1


def test_cli_list_llms_text(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["list-llms"])
    assert code == 0
    out = capsys.readouterr().out
    assert "cursor:composer-2.5" in out
    assert "openai:gpt-4o" in out


def test_cli_list_llms_json(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["list-llms", "--format", "json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == supported_llms()


def test_cli_invalid_llm(tmp_path: Path) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")
    code = main(
        [
            "translate",
            str(doc),
            "--job-id",
            "bad-llm",
            "--output-dir",
            str(tmp_path / "runs"),
            "--llm",
            "openai:not-a-real-model",
        ]
    )
    assert code == 1


def test_cli_invalid_target_lang_from_config(tmp_path: Path) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"target_lang": "spanish"}), encoding="utf-8")
    code = main(
        [
            "translate",
            str(doc),
            "--job-id",
            "bad-lang-cfg",
            "--output-dir",
            str(tmp_path / "runs"),
            "--config",
            str(config_file),
        ]
    )
    assert code == 1


def test_cli_configuration_error(tmp_path: Path) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")

    class FakeService:
        def __init__(self, config: PipelineConfig) -> None:
            pass

        def translate(self, input_path: Path, options):  # noqa: ANN001
            raise ConfigurationError("missing API key")

    with patch("document_translator.cli.DocumentTranslationService", FakeService):
        code = main(["translate", str(doc), "--job-id", "cfg-err", "--output-dir", str(tmp_path / "runs")])

    assert code == 1


def test_cli_failed_text_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")
    metadata = JobMetadata(job_id="fail-text", source_file="doc.txt")
    fake_result = JobResult(
        job_id="fail-text",
        status=JobStatus.FAILED,
        artifacts=ArtifactPaths(),
        metadata=metadata,
        error_message="extraction failed",
    )

    class FakeService:
        def __init__(self, config: PipelineConfig) -> None:
            pass

        def translate(self, input_path: Path, options):  # noqa: ANN001
            return fake_result

    with patch("document_translator.cli.DocumentTranslationService", FakeService):
        code = main(["translate", str(doc), "--job-id", "fail-text", "--output-dir", str(tmp_path / "runs")])

    assert code == 2
    assert "extraction failed" in capsys.readouterr().err


def test_cli_warnings_text_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")
    metadata = JobMetadata(
        job_id="warn-text",
        source_file="doc.txt",
        artifact_availability={"final_output": False, "resolved_md": False, "metadata_json": True, "status_json": True},
    )
    fake_result = JobResult(
        job_id="warn-text",
        status=JobStatus.COMPLETED_WITH_WARNINGS,
        artifacts=ArtifactPaths(metadata_json=tmp_path / "metadata.json", status_json=tmp_path / "status.json"),
        metadata=metadata,
    )

    class FakeService:
        def __init__(self, config: PipelineConfig) -> None:
            pass

        def translate(self, input_path: Path, options):  # noqa: ANN001
            return fake_result

    with patch("document_translator.cli.DocumentTranslationService", FakeService):
        code = main(["translate", str(doc), "--job-id", "warn-text", "--output-dir", str(tmp_path / "runs")])

    assert code == 3
    err = capsys.readouterr().err
    assert "Final document: not available" in err


@pytest.mark.integration
def test_cli_exit_code_warnings(spanish_contract: Path, tmp_path: Path) -> None:
    mock = MockLLMClient(prefix="[EN] ")

    with (
        patch("document_translator.pipeline.build_llm_client", return_value=mock),
        patch(
            "document_translator.pipeline.export_markdown",
            side_effect=RuntimeError("pandoc failed"),
        ),
    ):
        code = main(
            [
                "translate",
                str(spanish_contract),
                "--job-id",
                "cli-warn-exit",
                "--output-dir",
                str(tmp_path / "runs"),
                "--export-format",
                "pdf",
            ]
        )
    assert code == 3


def test_aggregate_exit_code_prefers_failure() -> None:
    jobs = [
        JobResult(
            job_id="ok",
            status=JobStatus.COMPLETED,
            artifacts=ArtifactPaths(),
            metadata=JobMetadata(job_id="ok", source_file="a.txt"),
        ),
        JobResult(
            job_id="bad",
            status=JobStatus.FAILED,
            artifacts=ArtifactPaths(),
            metadata=JobMetadata(job_id="bad", source_file="b.txt"),
        ),
    ]
    assert _aggregate_exit_code(jobs) == 2


def test_aggregate_exit_code_warnings_without_failure() -> None:
    jobs = [
        JobResult(
            job_id="ok",
            status=JobStatus.COMPLETED,
            artifacts=ArtifactPaths(),
            metadata=JobMetadata(job_id="ok", source_file="a.txt"),
        ),
        JobResult(
            job_id="warn",
            status=JobStatus.COMPLETED_WITH_WARNINGS,
            artifacts=ArtifactPaths(),
            metadata=JobMetadata(job_id="warn", source_file="b.txt"),
        ),
    ]
    assert _aggregate_exit_code(jobs) == 3


def test_cli_single_input_uses_translate_not_batch(tmp_path: Path) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")
    metadata = JobMetadata(job_id="single", source_file="doc.txt")
    fake_result = JobResult(
        job_id="single",
        status=JobStatus.COMPLETED,
        artifacts=ArtifactPaths(),
        metadata=metadata,
    )

    class FakeService:
        def __init__(self, config: PipelineConfig) -> None:
            self.config = config

        def translate(self, input_path: Path, options):  # noqa: ANN001
            return fake_result

        def translate_batch(self, items):  # noqa: ANN001
            raise AssertionError("translate_batch should not be called for single input")

    with patch("document_translator.cli.DocumentTranslationService", FakeService):
        code = main(
            [
                "translate",
                str(doc),
                "--job-id",
                "single",
                "--output-dir",
                str(tmp_path / "runs"),
            ]
        )

    assert code == 0


def test_cli_batch_calls_translate_batch(tmp_path: Path) -> None:
    doc_a = tmp_path / "a.txt"
    doc_b = tmp_path / "b.txt"
    doc_a.write_text("hello", encoding="utf-8")
    doc_b.write_text("world", encoding="utf-8")

    captured_items: list[tuple[Path, object]] = []

    def make_result(job_id: str, source_file: str) -> JobResult:
        return JobResult(
            job_id=job_id,
            status=JobStatus.COMPLETED,
            artifacts=ArtifactPaths(),
            metadata=JobMetadata(job_id=job_id, source_file=source_file),
        )

    class FakeService:
        def __init__(self, config: PipelineConfig) -> None:
            self.config = config

        def translate(self, input_path: Path, options):  # noqa: ANN001
            raise AssertionError("translate should not be called for batch CLI")

        def translate_batch(self, items):  # noqa: ANN001
            captured_items.extend(items)
            return BatchJobResult(
                jobs=[
                    make_result("job-a", "a.txt"),
                    make_result("job-b", "b.txt"),
                ],
                status=JobStatus.COMPLETED,
            )

    with patch("document_translator.cli.DocumentTranslationService", FakeService):
        code = main(
            [
                "translate",
                str(doc_a),
                str(doc_b),
                "--job-ids",
                "job-a",
                "job-b",
                "--output-dir",
                str(tmp_path / "runs"),
                "--target-lang",
                "es",
            ]
        )

    assert code == 0
    assert len(captured_items) == 2
    assert captured_items[0][0] == doc_a
    assert captured_items[1][0] == doc_b
    assert captured_items[0][1].job_id == "job-a"
    assert captured_items[1][1].job_id == "job-b"
    assert captured_items[0][1].target_lang == "es"


def test_cli_batch_json_envelope(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    doc_a = tmp_path / "a.txt"
    doc_b = tmp_path / "b.txt"
    doc_a.write_text("hello", encoding="utf-8")
    doc_b.write_text("world", encoding="utf-8")

    class FakeService:
        def __init__(self, config: PipelineConfig) -> None:
            pass

        def translate_batch(self, items):  # noqa: ANN001
            return BatchJobResult(
                jobs=[
                    JobResult(
                        job_id="job-a",
                        status=JobStatus.COMPLETED,
                        artifacts=ArtifactPaths(),
                        metadata=JobMetadata(job_id="job-a", source_file="a.txt"),
                    ),
                    JobResult(
                        job_id="job-b",
                        status=JobStatus.COMPLETED_WITH_WARNINGS,
                        artifacts=ArtifactPaths(),
                        metadata=JobMetadata(job_id="job-b", source_file="b.txt"),
                    ),
                ],
                status=JobStatus.COMPLETED_WITH_WARNINGS,
            )

    with patch("document_translator.cli.DocumentTranslationService", FakeService):
        code = main(
            [
                "translate",
                str(doc_a),
                str(doc_b),
                "--job-ids",
                "job-a",
                "job-b",
                "--output-dir",
                str(tmp_path / "runs"),
                "--format",
                "json",
            ]
        )

    assert code == 3
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "completed_with_warnings"
    assert payload["job_count"] == 2
    assert payload["completed_count"] == 1
    assert payload["completed_with_warnings_count"] == 1
    assert payload["failed_count"] == 0
    assert [job["job_id"] for job in payload["jobs"]] == ["job-a", "job-b"]


def test_cli_job_id_with_multiple_inputs_rejected(tmp_path: Path) -> None:
    doc_a = tmp_path / "a.txt"
    doc_b = tmp_path / "b.txt"
    doc_a.write_text("hello", encoding="utf-8")
    doc_b.write_text("world", encoding="utf-8")

    code = main(
        [
            "translate",
            str(doc_a),
            str(doc_b),
            "--job-id",
            "only-one",
            "--output-dir",
            str(tmp_path / "runs"),
        ]
    )
    assert code == 1


def test_cli_job_ids_count_mismatch(tmp_path: Path) -> None:
    doc_a = tmp_path / "a.txt"
    doc_b = tmp_path / "b.txt"
    doc_a.write_text("hello", encoding="utf-8")
    doc_b.write_text("world", encoding="utf-8")

    code = main(
        [
            "translate",
            str(doc_a),
            str(doc_b),
            "--job-ids",
            "only-one",
            "--output-dir",
            str(tmp_path / "runs"),
        ]
    )
    assert code == 1


def test_cli_batch_missing_input_fails_before_translate(tmp_path: Path) -> None:
    doc_a = tmp_path / "a.txt"
    doc_a.write_text("hello", encoding="utf-8")

    class FakeService:
        def __init__(self, config: PipelineConfig) -> None:
            raise AssertionError("service should not be constructed")

        def translate_batch(self, items):  # noqa: ANN001
            raise AssertionError("translate_batch should not be called")

    with patch("document_translator.cli.DocumentTranslationService", FakeService):
        code = main(
            [
                "translate",
                str(doc_a),
                str(tmp_path / "missing.txt"),
                "--output-dir",
                str(tmp_path / "runs"),
            ]
        )

    assert code == 1


def test_cli_batch_preflight_existing_job_dir(tmp_path: Path) -> None:
    doc_a = tmp_path / "a.txt"
    doc_b = tmp_path / "b.txt"
    doc_a.write_text("hello", encoding="utf-8")
    doc_b.write_text("world", encoding="utf-8")
    runs = tmp_path / "runs"
    (runs / "job-b").mkdir(parents=True)

    class FakeService:
        def __init__(self, config: PipelineConfig) -> None:
            raise AssertionError("service should not be constructed")

    with patch("document_translator.cli.DocumentTranslationService", FakeService):
        code = main(
            [
                "translate",
                str(doc_a),
                str(doc_b),
                "--job-ids",
                "job-a",
                "job-b",
                "--output-dir",
                str(runs),
            ]
        )

    assert code == 1


def test_cli_job_id_and_job_ids_rejected(tmp_path: Path) -> None:
    doc = tmp_path / "doc.txt"
    doc.write_text("hello", encoding="utf-8")

    code = main(
        [
            "translate",
            str(doc),
            "--job-id",
            "only-one",
            "--job-ids",
            "also-one",
            "--output-dir",
            str(tmp_path / "runs"),
        ]
    )
    assert code == 1


def test_cli_duplicate_job_ids_rejected(tmp_path: Path) -> None:
    doc_a = tmp_path / "a.txt"
    doc_b = tmp_path / "b.txt"
    doc_a.write_text("hello", encoding="utf-8")
    doc_b.write_text("world", encoding="utf-8")

    code = main(
        [
            "translate",
            str(doc_a),
            str(doc_b),
            "--job-ids",
            "same-id",
            "same-id",
            "--output-dir",
            str(tmp_path / "runs"),
        ]
    )
    assert code == 1


def test_cli_batch_exit_2_when_one_job_fails(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    doc_a = tmp_path / "a.txt"
    doc_b = tmp_path / "b.txt"
    doc_a.write_text("hello", encoding="utf-8")
    doc_b.write_text("world", encoding="utf-8")

    class FakeService:
        def __init__(self, config: PipelineConfig) -> None:
            pass

        def translate_batch(self, items):  # noqa: ANN001
            return BatchJobResult(
                jobs=[
                    JobResult(
                        job_id="job-a",
                        status=JobStatus.COMPLETED,
                        artifacts=ArtifactPaths(),
                        metadata=JobMetadata(job_id="job-a", source_file="a.txt"),
                    ),
                    JobResult(
                        job_id="job-b",
                        status=JobStatus.FAILED,
                        artifacts=ArtifactPaths(),
                        metadata=JobMetadata(job_id="job-b", source_file="b.txt"),
                        error_message="extract failed",
                    ),
                ],
                status=JobStatus.FAILED,
            )

    with patch("document_translator.cli.DocumentTranslationService", FakeService):
        code = main(
            [
                "translate",
                str(doc_a),
                str(doc_b),
                "--job-ids",
                "job-a",
                "job-b",
                "--output-dir",
                str(tmp_path / "runs"),
                "--format",
                "json",
            ]
        )

    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"
    assert payload["failed_count"] == 1
    assert payload["jobs"][1]["error_message"] == "extract failed"
