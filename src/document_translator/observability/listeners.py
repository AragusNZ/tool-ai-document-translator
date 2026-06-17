from __future__ import annotations

import logging
from collections.abc import Sequence

from document_translator.errors import IssueSeverity, PipelineIssue
from document_translator.observability.context import IssueContext
from document_translator.observability.logging_setup import get_logger

_SEVERITY_TO_LEVEL = {
    IssueSeverity.INFO: logging.INFO,
    IssueSeverity.WARN: logging.WARNING,
    IssueSeverity.ERROR: logging.ERROR,
}


class LoggingIssueListener:
    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or get_logger()

    def on_issue(
        self,
        issue: PipelineIssue,
        *,
        context: IssueContext,
        cause: BaseException | None = None,
    ) -> None:
        level = _SEVERITY_TO_LEVEL.get(issue.severity, logging.WARNING)
        self._logger.log(
            level,
            issue.message,
            extra={
                "job_id": context.job_id,
                "source_file": context.source_file,
                "issue_code": issue.code.value,
                "stage": issue.stage.value if issue.stage else None,
                "scope": issue.scope,
            },
            exc_info=(type(cause), cause, cause.__traceback__) if cause else None,
        )


class SentryIssueListener:
    def __init__(self, report_severities: Sequence[IssueSeverity]) -> None:
        self._report_severities = frozenset(report_severities)

    def on_issue(
        self,
        issue: PipelineIssue,
        *,
        context: IssueContext,
        cause: BaseException | None = None,
    ) -> None:
        try:
            import sentry_sdk
        except ImportError:
            return

        breadcrumb_data = {
            "code": issue.code.value,
            "severity": issue.severity.value,
            "message": issue.message,
            "stage": issue.stage.value if issue.stage else None,
            "scope": issue.scope,
            "job_id": context.job_id,
            "source_file": context.source_file,
        }
        if cause is not None:
            breadcrumb_data["cause_type"] = type(cause).__name__
            breadcrumb_data["cause_message"] = str(cause)

        sentry_sdk.add_breadcrumb(
            category="pipeline.issue",
            message=issue.message,
            level=_sentry_level(issue.severity),
            data=breadcrumb_data,
        )

        if issue.severity not in self._report_severities:
            return

        with sentry_sdk.push_scope() as scope:
            if context.job_id:
                scope.set_tag("job_id", context.job_id)
            if context.source_file:
                scope.set_tag("source_file", context.source_file)
            scope.set_tag("issue_code", issue.code.value)
            if issue.stage:
                scope.set_tag("stage", issue.stage.value)
            scope.set_context("issue", breadcrumb_data)
            if cause is not None:
                sentry_sdk.capture_exception(cause)
            else:
                sentry_sdk.capture_message(
                    issue.message,
                    level=_sentry_level(issue.severity),
                )


def _sentry_level(severity: IssueSeverity) -> str:
    if severity == IssueSeverity.ERROR:
        return "error"
    if severity == IssueSeverity.WARN:
        return "warning"
    return "info"
