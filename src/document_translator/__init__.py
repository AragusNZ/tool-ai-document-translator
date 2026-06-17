"""Document translation pipeline with quick and thorough translation modes."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("document-translator")
except PackageNotFoundError:
    __version__ = "0.0.0"

from document_translator.config.formats import ExportFormat
from document_translator.config.llms import LLMProvider, parse_llm_selector, supported_llms
from document_translator.config.settings import PipelineConfig
from document_translator.models import BatchJobResult, JobResult, JobSummary, TranslationOptions
from document_translator.pipeline import DocumentTranslationService
from document_translator.types import JobStatus, TranslationMode

__all__ = [
    "__version__",
    "DocumentTranslationService",
    "ExportFormat",
    "BatchJobResult",
    "JobResult",
    "JobSummary",
    "JobStatus",
    "LLMProvider",
    "PipelineConfig",
    "TranslationMode",
    "TranslationOptions",
    "parse_llm_selector",
    "supported_llms",
]
