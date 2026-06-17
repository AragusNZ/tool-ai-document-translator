from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from document_translator.errors import IssueCode, IssueSeverity
from document_translator.config.settings import PipelineConfig
from document_translator.models import ExtractionAlert, TranslationOptions
from document_translator.observability import (
    build_issue_listeners,
    configure_observability,
    parse_sentry_report_severities,
)
from document_translator.observability.context import IssueContext
from document_translator.observability.listeners import LoggingIssueListener, SentryIssueListener
from document_translator.observability.logging_setup import JsonLogFormatter, configure_logging
from document_translator.pipeline import DocumentTranslationService
from document_translator.report.collector import IssueCollector
from document_translator.lib.llm import MockLLMClient
from document_translator.types import PipelineStage


class RecordingListener:
    def __init__(self) -> None:
        self.issues: list[tuple[object, IssueContext, BaseException | None]] = []

    def on_issue(
        self,
        issue,
        *,
        context: IssueContext,
        cause: BaseException | None = None,
    ) -> None:
        self.issues.append((issue, context, cause))


class BrokenListener:
    def on_issue(
        self,
        issue,
        *,
        context: IssueContext,
        cause: BaseException | None = None,
    ) -> None:
        raise RuntimeError("listener failed")


def test_issue_collector_notifies_listeners() -> None:
    listener = RecordingListener()
    collector = IssueCollector([listener])
    collector.set_context(job_id="job-1", source_file="doc.txt")
    collector.add(IssueCode.EXPORT_FAILED, IssueSeverity.WARN, "pdf failed", stage=PipelineStage.EXPORTING)

    alert = ExtractionAlert(code="EMPTY_EXTRACTION", message="no text", scope={"file": "doc.txt"})
    collector.add_from_alert(alert, stage=PipelineStage.EXTRACTING)

    assert len(listener.issues) == 2
    _, ctx, _cause = listener.issues[0]
    assert ctx.job_id == "job-1"
    assert ctx.source_file == "doc.txt"


def test_issue_collector_extend_notifies_listeners() -> None:
    from document_translator.errors import PipelineIssue

    listener = RecordingListener()
    collector = IssueCollector([listener])
    issue = PipelineIssue(
        code=IssueCode.LLM_RESPONSE_PARSE_FAILED,
        severity=IssueSeverity.WARN,
        message="parse failed",
    )
    collector.extend([issue])
    assert len(listener.issues) == 1
    assert listener.issues[0][0].code == IssueCode.LLM_RESPONSE_PARSE_FAILED


def test_listener_exception_does_not_break_collector() -> None:
    collector = IssueCollector([BrokenListener()])
    collector.add(IssueCode.PIPELINE_FAILED, IssueSeverity.ERROR, "boom")
    assert len(collector.to_list()) == 1


def test_logging_listener_severity_mapping(caplog: pytest.LogCaptureFixture) -> None:
    from document_translator.errors import PipelineIssue

    logger = logging.getLogger("document_translator.test")
    listener = LoggingIssueListener(logger=logger)
    context = IssueContext(job_id="j1", source_file="a.txt")

    with caplog.at_level(logging.DEBUG, logger="document_translator.test"):
        listener.on_issue(
            PipelineIssue(code=IssueCode.EXPORT_FAILED, severity=IssueSeverity.WARN, message="warn issue"),
            context=context,
        )

    assert "warn issue" in caplog.text


def test_logging_listener_maps_all_severities(caplog: pytest.LogCaptureFixture) -> None:
    from document_translator.errors import PipelineIssue

    logger = logging.getLogger("document_translator.test.severity")
    listener = LoggingIssueListener(logger=logger)
    context = IssueContext(job_id="j1", source_file="a.txt")

    with caplog.at_level(logging.DEBUG, logger="document_translator.test.severity"):
        for severity, level_name in (
            (IssueSeverity.INFO, "INFO"),
            (IssueSeverity.WARN, "WARNING"),
            (IssueSeverity.ERROR, "ERROR"),
        ):
            listener.on_issue(
                PipelineIssue(code=IssueCode.PIPELINE_FAILED, severity=severity, message=f"{level_name} msg"),
                context=context,
            )

    assert "INFO msg" in caplog.text
    assert "WARNING msg" in caplog.text
    assert "ERROR msg" in caplog.text


@pytest.fixture
def mock_sentry_sdk():
    mock = MagicMock()
    with patch.dict(sys.modules, {"sentry_sdk": mock}):
        yield mock


def test_sentry_listener_errors_only_by_default(mock_sentry_sdk: MagicMock) -> None:
    from document_translator.errors import PipelineIssue

    listener = SentryIssueListener(report_severities=[IssueSeverity.ERROR])
    context = IssueContext(job_id="j1", source_file="a.txt")

    listener.on_issue(
        PipelineIssue(code=IssueCode.EXPORT_FAILED, severity=IssueSeverity.WARN, message="warn"),
        context=context,
    )
    listener.on_issue(
        PipelineIssue(code=IssueCode.PIPELINE_FAILED, severity=IssueSeverity.ERROR, message="error"),
        context=context,
    )

    assert mock_sentry_sdk.add_breadcrumb.call_count == 2
    assert mock_sentry_sdk.capture_message.call_count == 1


def test_sentry_listener_captures_cause(mock_sentry_sdk: MagicMock) -> None:
    from document_translator.errors import PipelineIssue

    listener = SentryIssueListener(report_severities=[IssueSeverity.ERROR])
    context = IssueContext(job_id="j1", source_file="a.txt")
    cause = RuntimeError("sdk down")

    listener.on_issue(
        PipelineIssue(code=IssueCode.PIPELINE_FAILED, severity=IssueSeverity.ERROR, message="wrapped"),
        context=context,
        cause=cause,
    )

    mock_sentry_sdk.capture_exception.assert_called_once_with(cause)
    mock_sentry_sdk.capture_message.assert_not_called()


def test_sentry_listener_respects_report_severities(mock_sentry_sdk: MagicMock) -> None:
    from document_translator.errors import PipelineIssue

    listener = SentryIssueListener(report_severities=[IssueSeverity.ERROR, IssueSeverity.WARN])
    context = IssueContext(job_id="j1", source_file="a.txt")

    listener.on_issue(
        PipelineIssue(code=IssueCode.EXPORT_FAILED, severity=IssueSeverity.WARN, message="warn"),
        context=context,
    )
    listener.on_issue(
        PipelineIssue(code=IssueCode.PIPELINE_FAILED, severity=IssueSeverity.ERROR, message="error"),
        context=context,
    )

    assert mock_sentry_sdk.capture_message.call_count == 2


def test_configure_observability_no_sentry_without_dsn() -> None:
    config = PipelineConfig(sentry_dsn=None)
    configure_observability(config)


def test_parse_sentry_report_severities() -> None:
    assert parse_sentry_report_severities("error,warn") == [IssueSeverity.ERROR, IssueSeverity.WARN]
    assert parse_sentry_report_severities("") == [IssueSeverity.ERROR]


def test_json_log_formatter() -> None:
    record = logging.LogRecord(
        name="document_translator",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="stage complete",
        args=(),
        exc_info=None,
    )
    record.job_id = "job-1"
    record.stage = "extracting"
    payload = json.loads(JsonLogFormatter().format(record))
    assert payload["message"] == "stage complete"
    assert payload["job_id"] == "job-1"
    assert payload["stage"] == "extracting"


def test_build_issue_listeners_without_sentry() -> None:
    config = PipelineConfig(sentry_dsn=None)
    listeners = build_issue_listeners(config)
    assert len(listeners) == 1
    assert isinstance(listeners[0], LoggingIssueListener)


def test_build_issue_listeners_with_sentry() -> None:
    config = PipelineConfig(sentry_dsn="https://example@o0.ingest.sentry.io/0")
    listeners = build_issue_listeners(config)
    assert len(listeners) == 2
    assert isinstance(listeners[1], SentryIssueListener)


def test_pipeline_logs_stage_transitions(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    text = "POR CUANTO las partes convienen en celebrar el presente contrato legal.\n" * 5
    path = tmp_path / "contract.txt"
    path.write_text(text, encoding="utf-8")

    config = PipelineConfig(runs_dir=tmp_path / "runs", root=tmp_path, log_level="INFO")
    service = DocumentTranslationService(
        config=config,
        llm=MockLLMClient(prefix="[EN] "),
        issue_listeners=[],
    )

    with caplog.at_level(logging.INFO, logger="document_translator"):
        with patch("document_translator.pipeline.export_markdown"):
            service.translate(path, TranslationOptions(job_id="log-job"))

    assert any(getattr(record, "job_id", None) == "log-job" for record in caplog.records)
    assert any(getattr(record, "stage", None) == "extracting" for record in caplog.records)
    assert any("Extracting document" in record.message for record in caplog.records)


def test_collector_has_warnings() -> None:
    from document_translator.errors import IssueCode
    from document_translator.report.collector import IssueCollector

    c = IssueCollector()
    assert not c.has_warnings()
    c.add(IssueCode.EXPORT_FAILED, IssueSeverity.WARN, "x")
    assert c.has_warnings()
