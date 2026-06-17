from __future__ import annotations

import os
import time
from pathlib import Path

from document_translator.config.defaults import (
    DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_RETRY_BASE_DELAY,
    DEFAULT_RETRY_MAX_DELAY,
    DEFAULT_TRANSLATION_MODEL,
)
from document_translator.errors import IssueCode, PipelineError
from document_translator.lib.llm.protocol import LLMCallTracker
from document_translator.lib.llm.retry import retry_delay_seconds
from document_translator.lib.llm.tokens import estimate_tokens_from_text
from document_translator.observability.logging_setup import get_logger
from document_translator.types import PipelineStage

logger = get_logger(__name__)


class CursorLLMClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = DEFAULT_TRANSLATION_MODEL,
        cwd: Path | None = None,
        tracker: LLMCallTracker | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_base_delay: float = DEFAULT_RETRY_BASE_DELAY,
        retry_max_delay: float = DEFAULT_RETRY_MAX_DELAY,
        request_timeout_seconds: float = DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self.api_key = api_key or os.environ.get("CURSOR_API_KEY")
        self.model = model
        self.cwd = cwd or Path.cwd()
        self.tracker = tracker or LLMCallTracker()
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay
        self.retry_max_delay = retry_max_delay
        self.request_timeout_seconds = request_timeout_seconds

    def complete(self, system: str, user: str) -> str:
        if not self.api_key:
            raise PipelineError(
                "CURSOR_API_KEY is required for translation",
                code=IssueCode.CONFIGURATION_ERROR,
                stage=PipelineStage.TRANSLATING,
            )

        from cursor_sdk import Agent, AgentOptions, CursorAgentError, LocalAgentOptions

        prompt = f"{system}\n\n---\n\n{user}"

        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                result = Agent.prompt(
                    prompt,
                    AgentOptions(
                        api_key=self.api_key,
                        model=self.model,
                        local=LocalAgentOptions(cwd=str(self.cwd), setting_sources=[]),
                    ),
                )
            except CursorAgentError as exc:
                last_exc = exc
                if not exc.is_retryable or attempt >= self.max_retries:
                    raise PipelineError(
                        f"Cursor SDK request failed: {exc}",
                        code=IssueCode.PIPELINE_FAILED,
                        stage=PipelineStage.TRANSLATING,
                        cause=exc,
                    ) from exc
                delay = retry_delay_seconds(
                    exc,
                    attempt,
                    base_delay=self.retry_base_delay,
                    max_delay=self.retry_max_delay,
                )
                logger.warning(
                    "Cursor SDK rate limited or transient error (attempt %s/%s); retrying in %.1fs: %s",
                    attempt + 1,
                    self.max_retries + 1,
                    delay,
                    exc,
                )
                time.sleep(delay)
                continue
            except Exception as exc:
                raise PipelineError(
                    f"Cursor SDK startup failed: {exc}",
                    code=IssueCode.PIPELINE_FAILED,
                    stage=PipelineStage.TRANSLATING,
                    cause=exc,
                ) from exc
            else:
                break
        else:
            assert last_exc is not None
            raise PipelineError(
                f"Cursor SDK request failed after {self.max_retries + 1} attempts: {last_exc}",
                code=IssueCode.PIPELINE_FAILED,
                stage=PipelineStage.TRANSLATING,
                cause=last_exc,
            ) from last_exc

        if result.status == "error":
            raise PipelineError(
                f"Cursor agent run failed: {result.id}",
                code=IssueCode.PIPELINE_FAILED,
                stage=PipelineStage.TRANSLATING,
                scope={"run_id": str(result.id)},
            )
        text = (result.result or "").strip()
        if not text:
            raise PipelineError(
                "Cursor agent returned empty response",
                code=IssueCode.PIPELINE_FAILED,
                stage=PipelineStage.TRANSLATING,
                scope={"run_id": str(result.id)},
            )
        if self.tracker:
            self.tracker.record(
                input_tokens=estimate_tokens_from_text(prompt),
                output_tokens=estimate_tokens_from_text(text),
            )
        return text
