from __future__ import annotations

from importlib import import_module
from pathlib import Path

from document_translator.config.llms import LLMProvider, parse_llm_selector
from document_translator.config.settings import PipelineConfig
from document_translator.errors import IssueCode, PipelineError
from document_translator.lib.llm.cursor import CursorLLMClient
from document_translator.lib.llm.protocol import LLMCallTracker, LLMClient
from document_translator.types import PipelineStage


def build_llm_client(
    config: PipelineConfig,
    *,
    tracker: LLMCallTracker,
    cwd: Path,
) -> LLMClient:
    provider, model = parse_llm_selector(config.llm)
    match provider:
        case LLMProvider.CURSOR:
            return CursorLLMClient(
                api_key=config.cursor_api_key,
                model=model,
                cwd=cwd,
                tracker=tracker,
                request_timeout_seconds=config.llm_request_timeout_seconds,
            )
        case LLMProvider.OPENAI:
            _require_optional_dependency("openai", provider)
            from document_translator.lib.llm.openai import OpenAILLMClient

            return OpenAILLMClient(
                api_key=config.openai_api_key,
                model=model,
                tracker=tracker,
                request_timeout_seconds=config.llm_request_timeout_seconds,
            )
        case LLMProvider.ANTHROPIC:
            _require_optional_dependency("anthropic", provider)
            from document_translator.lib.llm.anthropic import AnthropicLLMClient

            return AnthropicLLMClient(
                api_key=config.anthropic_api_key,
                model=model,
                tracker=tracker,
                request_timeout_seconds=config.llm_request_timeout_seconds,
            )
        case LLMProvider.GOOGLE:
            _require_optional_dependency("google.genai", provider)
            from document_translator.lib.llm.google import GoogleLLMClient

            return GoogleLLMClient(
                api_key=config.google_api_key,
                model=model,
                tracker=tracker,
                request_timeout_seconds=config.llm_request_timeout_seconds,
            )
        case _:
            raise PipelineError(
                f"Unsupported LLM provider: {provider.value}",
                code=IssueCode.CONFIGURATION_ERROR,
                stage=PipelineStage.TRANSLATING,
            )


def _require_optional_dependency(module_name: str, provider: LLMProvider) -> None:
    try:
        import_module(module_name)
    except ImportError as exc:
        raise PipelineError(
            f"LLM provider {provider.value!r} requires optional dependency {module_name!r}; "
            f"install with pip install 'document-translator[{provider.value}]'",
            code=IssueCode.CONFIGURATION_ERROR,
            stage=PipelineStage.TRANSLATING,
            cause=exc,
        ) from exc
