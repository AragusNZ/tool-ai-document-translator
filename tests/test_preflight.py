from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from document_translator.config.formats import ExportFormat
from document_translator.config.settings import PipelineConfig
from document_translator.errors import IssueCode, JobCancelledError, JobTimeoutError
from document_translator.lib.job_control import (
    JobDeadline,
    is_job_cancelled,
    request_job_cancel,
    reset_job_control,
)
from document_translator.lib.preflight import CheckStatus, run_preflight_checks
from document_translator.types import PipelineStage


def test_job_deadline_not_expired() -> None:
    deadline = JobDeadline(60.0, started=100.0)
    with patch("document_translator.lib.job_control.time.monotonic", return_value=120.0):
        deadline.check(PipelineStage.TRANSLATING)


def test_job_deadline_expired_raises() -> None:
    deadline = JobDeadline(10.0, started=100.0)
    with patch("document_translator.lib.job_control.time.monotonic", return_value=111.0):
        with pytest.raises(JobTimeoutError) as exc_info:
            deadline.check(PipelineStage.TRANSLATING)
    assert exc_info.value.code == IssueCode.JOB_TIMEOUT
    assert exc_info.value.stage == PipelineStage.TRANSLATING


def test_job_cancelled_raises() -> None:
    reset_job_control()
    request_job_cancel()
    deadline = JobDeadline(None)
    with pytest.raises(JobCancelledError) as exc_info:
        deadline.check(PipelineStage.EXPORTING)
    assert exc_info.value.code == IssueCode.JOB_CANCELLED
    assert is_job_cancelled()


def test_preflight_ready_with_mocks(tmp_path: Path) -> None:
    config = PipelineConfig(
        runs_dir=tmp_path / "runs",
        llm="cursor:composer-2.5",
        cursor_api_key="test-key",
        pdf_ocr=False,
    )
    with (
        patch("document_translator.lib.preflight.shutil.which", return_value="/usr/bin/pandoc"),
        patch("document_translator.lib.preflight.import_module"),
        patch("document_translator.lib.preflight.tesseract_available", return_value=False),
    ):
        with patch.dict("sys.modules", {"weasyprint": object()}):
            result = run_preflight_checks(config, export_format=ExportFormat.MD)

    assert result.ready
    assert any(check.name == "llm_api_key" and check.status == CheckStatus.OK for check in result.checks)
    assert not any(check.name == "pandoc" for check in result.checks)


def test_preflight_fails_without_api_key(tmp_path: Path) -> None:
    config = PipelineConfig(
        runs_dir=tmp_path / "runs",
        llm="cursor:composer-2.5",
        cursor_api_key=None,
        pdf_ocr=False,
    )
    with (
        patch("document_translator.lib.preflight.shutil.which", return_value="/usr/bin/pandoc"),
        patch("document_translator.lib.preflight.import_module"),
        patch.dict("sys.modules", {"weasyprint": object()}),
    ):
        result = run_preflight_checks(config, export_format=ExportFormat.PDF)

    assert not result.ready
    api_check = next(check for check in result.checks if check.name == "llm_api_key")
    assert api_check.status == CheckStatus.FAIL


def test_preflight_pdf_requires_pandoc_and_weasyprint(tmp_path: Path) -> None:
    import builtins

    config = PipelineConfig(
        runs_dir=tmp_path / "runs",
        llm="cursor:composer-2.5",
        cursor_api_key="key",
        pdf_ocr=False,
    )
    real_import = builtins.__import__

    def _import(name: str, *args, **kwargs):  # noqa: ANN002, ANN003
        if name == "weasyprint":
            raise ImportError("no weasyprint")
        return real_import(name, *args, **kwargs)

    with (
        patch("document_translator.lib.preflight.shutil.which", return_value=None),
        patch("document_translator.lib.preflight.import_module"),
        patch("builtins.__import__", side_effect=_import),
    ):
        result = run_preflight_checks(config, export_format=ExportFormat.PDF)

    assert not result.ready
    assert any(check.name == "pandoc" and check.status == CheckStatus.FAIL for check in result.checks)
    assert any(check.name == "weasyprint" and check.status == CheckStatus.FAIL for check in result.checks)


def test_preflight_tesseract_required(tmp_path: Path) -> None:
    config = PipelineConfig(
        runs_dir=tmp_path / "runs",
        llm="cursor:composer-2.5",
        cursor_api_key="key",
        pdf_ocr=True,
    )
    with (
        patch("document_translator.lib.preflight.shutil.which", return_value="/usr/bin/pandoc"),
        patch("document_translator.lib.preflight.import_module"),
        patch("document_translator.lib.preflight.tesseract_available", return_value=False),
        patch.dict("sys.modules", {"weasyprint": object()}),
    ):
        result = run_preflight_checks(config, export_format=ExportFormat.PDF, require_ocr=True)

    tess = next(check for check in result.checks if check.name == "tesseract")
    assert tess.status == CheckStatus.FAIL
    assert not result.ready


def test_preflight_runs_dir_not_writable(tmp_path: Path) -> None:
    config = PipelineConfig(
        runs_dir=tmp_path / "runs",
        llm="cursor:composer-2.5",
        cursor_api_key="key",
        pdf_ocr=False,
    )
    with (
        patch("document_translator.lib.preflight.shutil.which", return_value="/usr/bin/pandoc"),
        patch("document_translator.lib.preflight.import_module"),
        patch.dict("sys.modules", {"weasyprint": object()}),
        patch(
            "document_translator.lib.preflight.Path.write_text",
            side_effect=OSError("permission denied"),
        ),
    ):
        result = run_preflight_checks(config, export_format=ExportFormat.PDF)

    runs_check = next(check for check in result.checks if check.name == "runs_dir")
    assert runs_check.status == CheckStatus.FAIL
    assert not result.ready


def test_preflight_odt_export_requires_pandoc(tmp_path: Path) -> None:
    config = PipelineConfig(
        runs_dir=tmp_path / "runs",
        llm="cursor:composer-2.5",
        cursor_api_key="key",
        pdf_ocr=False,
    )
    with (
        patch("document_translator.lib.preflight.shutil.which", return_value=None),
        patch("document_translator.lib.preflight.import_module"),
    ):
        result = run_preflight_checks(config, export_format=ExportFormat.ODT)

    assert not result.ready
    assert any(check.name == "pandoc" and check.status == CheckStatus.FAIL for check in result.checks)


def test_preflight_liteparse_backend_requires_stack(tmp_path: Path) -> None:
    import importlib

    config = PipelineConfig(
        runs_dir=tmp_path / "runs",
        llm="cursor:composer-2.5",
        cursor_api_key="key",
        pdf_ocr=False,
        extract_backend="liteparse",
    )

    def _which(cmd: str) -> str | None:
        if cmd in {"pandoc", "convert"}:
            return f"/usr/bin/{cmd}"
        return None

    def _import_module(name: str, *args, **kwargs):  # noqa: ANN002, ANN003
        if name == "liteparse":
            raise ImportError("no liteparse")
        return importlib.import_module(name, *args, **kwargs)

    with (
        patch("document_translator.lib.preflight.shutil.which", side_effect=_which),
        patch("document_translator.lib.preflight.import_module", side_effect=_import_module),
        patch.dict("sys.modules", {"weasyprint": object()}),
    ):
        result = run_preflight_checks(config, export_format=ExportFormat.PDF)

    assert not result.ready
    liteparse = next(check for check in result.checks if check.name == "liteparse")
    assert liteparse.status == CheckStatus.FAIL
    libreoffice = next(check for check in result.checks if check.name == "libreoffice")
    assert libreoffice.status == CheckStatus.FAIL
    imagemagick = next(check for check in result.checks if check.name == "imagemagick")
    assert imagemagick.status == CheckStatus.OK


def test_preflight_auto_backend_warns_on_missing_liteparse_stack(tmp_path: Path) -> None:
    import importlib

    config = PipelineConfig(
        runs_dir=tmp_path / "runs",
        llm="cursor:composer-2.5",
        cursor_api_key="key",
        pdf_ocr=False,
        extract_backend="auto",
    )

    def _import_module(name: str, *args, **kwargs):  # noqa: ANN002, ANN003
        if name == "liteparse":
            raise ImportError("no liteparse")
        return importlib.import_module(name, *args, **kwargs)

    with (
        patch("document_translator.lib.preflight.shutil.which", return_value=None),
        patch("document_translator.lib.preflight.import_module", side_effect=_import_module),
        patch.dict("sys.modules", {"weasyprint": object()}),
    ):
        result = run_preflight_checks(config, export_format=ExportFormat.MD)

    assert result.ready
    liteparse = next(check for check in result.checks if check.name == "liteparse")
    assert liteparse.status == CheckStatus.WARN
    assert liteparse.required is False
    imagemagick = next(check for check in result.checks if check.name == "imagemagick")
    assert imagemagick.status == CheckStatus.WARN
