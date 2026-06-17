from __future__ import annotations

from document_translator.config.settings import PipelineConfig
from document_translator.errors import IssueSeverity
from document_translator.observability.context import IssueContext, IssueListener
from document_translator.observability.listeners import LoggingIssueListener, SentryIssueListener
from document_translator.observability.logging_setup import configure_logging, get_logger
from document_translator.observability.sentry_setup import (
    capture_sentry_exception,
    finish_sentry_transaction,
    init_sentry,
    sentry_translate_transaction,
)


def parse_sentry_report_severities(raw: str | list[str]) -> list[IssueSeverity]:
    if isinstance(raw, str):
        parts = [p.strip().lower() for p in raw.split(",") if p.strip()]
    else:
        parts = [p.strip().lower() for p in raw if p.strip()]
    mapping = {
        "info": IssueSeverity.INFO,
        "warn": IssueSeverity.WARN,
        "warning": IssueSeverity.WARN,
        "error": IssueSeverity.ERROR,
    }
    result: list[IssueSeverity] = []
    for part in parts:
        severity = mapping.get(part)
        if severity and severity not in result:
            result.append(severity)
    return result or [IssueSeverity.ERROR]


def build_issue_listeners(config: PipelineConfig) -> list[IssueListener]:
    listeners: list[IssueListener] = [LoggingIssueListener()]
    if config.sentry_dsn:
        severities = parse_sentry_report_severities(config.sentry_report_severities)
        listeners.append(SentryIssueListener(report_severities=severities))
    return listeners


def configure_observability(config: PipelineConfig) -> None:
    configure_logging(config)
    init_sentry(config)


__all__ = [
    "IssueContext",
    "IssueListener",
    "LoggingIssueListener",
    "SentryIssueListener",
    "build_issue_listeners",
    "capture_sentry_exception",
    "configure_logging",
    "configure_observability",
    "finish_sentry_transaction",
    "get_logger",
    "init_sentry",
    "parse_sentry_report_severities",
    "sentry_translate_transaction",
]
