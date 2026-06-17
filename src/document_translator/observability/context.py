from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from document_translator.errors import PipelineIssue


@dataclass(frozen=True)
class IssueContext:
    job_id: str | None = None
    source_file: str | None = None


class IssueListener(Protocol):
    def on_issue(
        self,
        issue: PipelineIssue,
        *,
        context: IssueContext,
        cause: BaseException | None = None,
    ) -> None: ...
