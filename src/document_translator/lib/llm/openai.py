from __future__ import annotations

import os

from document_translator.config.defaults import (
    DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_RETRY_BASE_DELAY,
    DEFAULT_RETRY_MAX_DELAY,
)
from document_translator.errors import IssueCode, PipelineError
from document_translator.lib.llm.protocol import LLMCallTracker
from document_translator.lib.llm.retry import (
    is_retryable_http_status,
    retry_on_transient,
)
from document_translator.types import PipelineStage


class OpenAILLMClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "gpt-4o",
        tracker: LLMCallTracker | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_base_delay: float = DEFAULT_RETRY_BASE_DELAY,
        retry_max_delay: float = DEFAULT_RETRY_MAX_DELAY,
        request_timeout_seconds: float = DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.model = model
        self.tracker = tracker or LLMCallTracker()
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay
        self.retry_max_delay = retry_max_delay
        self.request_timeout_seconds = request_timeout_seconds

    def complete(self, system: str, user: str) -> str:
        if not self.api_key:
            raise PipelineError(
                "OPENAI_API_KEY is required for OpenAI translation",
                code=IssueCode.CONFIGURATION_ERROR,
                stage=PipelineStage.TRANSLATING,
            )

        from openai import APIStatusError, OpenAI

        client = OpenAI(api_key=self.api_key, timeout=self.request_timeout_seconds)
        usage_holder: list[tuple[int, int]] = []

        def _call() -> str:
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            text = (response.choices[0].message.content or "").strip()
            if not text:
                raise PipelineError(
                    "OpenAI returned empty response",
                    code=IssueCode.PIPELINE_FAILED,
                    stage=PipelineStage.TRANSLATING,
                )
            usage = getattr(response, "usage", None)
            input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
            output_tokens = int(getattr(usage, "completion_tokens", 0) or 0) if usage else 0
            usage_holder[:] = [(input_tokens, output_tokens)]
            return text

        def _is_retryable(exc: Exception) -> bool:
            if isinstance(exc, APIStatusError):
                return is_retryable_http_status(exc.status_code)
            return False

        def _retry_after(exc: Exception) -> str | None:
            if isinstance(exc, APIStatusError) and exc.response is not None:
                return exc.response.headers.get("retry-after")
            return None

        try:
            text = retry_on_transient(
                _call,
                is_retryable=_is_retryable,
                max_retries=self.max_retries,
                base_delay=self.retry_base_delay,
                max_delay=self.retry_max_delay,
                retry_after_for=_retry_after,
                log_label="OpenAI request",
            )
        except PipelineError:
            raise
        except Exception as exc:
            raise PipelineError(
                f"OpenAI request failed: {exc}",
                code=IssueCode.PIPELINE_FAILED,
                stage=PipelineStage.TRANSLATING,
                cause=exc,
            ) from exc
        else:
            if self.tracker and usage_holder:
                input_tokens, output_tokens = usage_holder[0]
                self.tracker.record(input_tokens=input_tokens, output_tokens=output_tokens)
            return text
