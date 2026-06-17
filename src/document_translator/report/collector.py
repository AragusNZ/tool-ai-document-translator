from __future__ import annotations

from collections.abc import Sequence

from document_translator.errors import IssueCode, IssueSeverity, PipelineIssue
from document_translator.models import ExtractionAlert
from document_translator.observability.context import IssueContext, IssueListener
from document_translator.observability.logging_setup import get_logger
from document_translator.types import PipelineStage

_logger = get_logger()


class IssueCollector:
    def __init__(self, listeners: Sequence[IssueListener] = ()) -> None:
        self._issues: list[PipelineIssue] = []
        self._listeners = list(listeners)
        self._context = IssueContext()

    def set_context(self, **kwargs: str | None) -> None:
        data = {**self._context.__dict__, **kwargs}
        self._context = IssueContext(
            job_id=data.get("job_id"),
            source_file=data.get("source_file"),
        )

    def add(
        self,
        code: IssueCode,
        severity: IssueSeverity,
        message: str,
        *,
        stage: PipelineStage | None = None,
        scope: dict[str, str] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        issue = PipelineIssue(
            code=code,
            severity=severity,
            message=message,
            stage=stage,
            scope=scope or {},
        )
        self._issues.append(issue)
        self._notify(issue, cause=cause)

    def add_from_alert(self, alert: ExtractionAlert, *, stage: PipelineStage) -> None:
        try:
            code = IssueCode(alert.code)
        except ValueError:
            code = IssueCode.PIPELINE_FAILED
        severity = IssueSeverity.WARN
        if alert.severity == "error":
            severity = IssueSeverity.ERROR
        elif alert.severity == "info":
            severity = IssueSeverity.INFO
        self.add(code, severity, alert.message, stage=stage, scope=alert.scope)

    def extend(self, issues: list[PipelineIssue]) -> None:
        for issue in issues:
            self._issues.append(issue)
            self._notify(issue)

    def has_errors(self) -> bool:
        return any(i.severity == IssueSeverity.ERROR for i in self._issues)

    def has_warnings(self) -> bool:
        return any(i.severity in (IssueSeverity.WARN, IssueSeverity.ERROR) for i in self._issues)

    def to_list(self) -> list[PipelineIssue]:
        return list(self._issues)

    def _notify(self, issue: PipelineIssue, *, cause: BaseException | None = None) -> None:
        for listener in self._listeners:
            try:
                listener.on_issue(issue, context=self._context, cause=cause)
            except Exception:
                _logger.debug("Issue listener failed", exc_info=True)
