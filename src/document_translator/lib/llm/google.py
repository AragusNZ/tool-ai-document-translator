from __future__ import annotations

import os

from document_translator.errors import IssueCode, PipelineError
from document_translator.lib.llm.protocol import LLMCallTracker
from document_translator.lib.llm.retry import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_RETRY_BASE_DELAY,
    DEFAULT_RETRY_MAX_DELAY,
    is_retryable_http_status,
    retry_on_transient,
)
from document_translator.types import PipelineStage


class GoogleLLMClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "gemini-2.5-pro",
        tracker: LLMCallTracker | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_base_delay: float = DEFAULT_RETRY_BASE_DELAY,
        retry_max_delay: float = DEFAULT_RETRY_MAX_DELAY,
    ) -> None:
        self.api_key = api_key or os.environ.get("GOOGLE_API_KEY")
        self.model = model
        self.tracker = tracker or LLMCallTracker()
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay
        self.retry_max_delay = retry_max_delay

    def complete(self, system: str, user: str) -> str:
        if not self.api_key:
            raise PipelineError(
                "GOOGLE_API_KEY is required for Google Gemini translation",
                code=IssueCode.CONFIGURATION_ERROR,
                stage=PipelineStage.TRANSLATING,
            )

        from google import genai

        client = genai.Client(api_key=self.api_key)
        usage_holder: list[tuple[int, int]] = []

        def _call() -> str:
            response = client.models.generate_content(
                model=self.model,
                contents=user,
                config={"system_instruction": system},
            )
            text = (response.text or "").strip()
            if not text:
                raise PipelineError(
                    "Google Gemini returned empty response",
                    code=IssueCode.PIPELINE_FAILED,
                    stage=PipelineStage.TRANSLATING,
                )
            usage = getattr(response, "usage_metadata", None)
            input_tokens = int(getattr(usage, "prompt_token_count", 0) or 0) if usage else 0
            output_tokens = int(getattr(usage, "candidates_token_count", 0) or 0) if usage else 0
            usage_holder[:] = [(input_tokens, output_tokens)]
            return text

        def _is_retryable(exc: Exception) -> bool:
            code = getattr(exc, "code", None)
            return isinstance(code, int) and is_retryable_http_status(code)

        def _retry_after(exc: Exception) -> str | None:
            response = getattr(exc, "response", None)
            headers = getattr(response, "headers", None)
            if headers is not None:
                return headers.get("retry-after")
            return None

        try:
            text = retry_on_transient(
                _call,
                is_retryable=_is_retryable,
                max_retries=self.max_retries,
                base_delay=self.retry_base_delay,
                max_delay=self.retry_max_delay,
                retry_after_for=_retry_after,
                log_label="Google Gemini request",
            )
        except PipelineError:
            raise
        except Exception as exc:
            raise PipelineError(
                f"Google Gemini request failed: {exc}",
                code=IssueCode.PIPELINE_FAILED,
                stage=PipelineStage.TRANSLATING,
                cause=exc,
            ) from exc
        else:
            if self.tracker and usage_holder:
                input_tokens, output_tokens = usage_holder[0]
                self.tracker.record(input_tokens=input_tokens, output_tokens=output_tokens)
            return text
