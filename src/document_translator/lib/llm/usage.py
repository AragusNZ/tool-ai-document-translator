from __future__ import annotations

from document_translator.lib.llm.pricing import estimate_llm_cost_usd
from document_translator.lib.llm.protocol import LLMCallTracker
from document_translator.models import JobMetadata, LLMUsage


def sync_tracker_to_metadata(
    metadata: JobMetadata,
    tracker: LLMCallTracker,
    *,
    llm_selector: str,
) -> None:
    metadata.llm_call_count = tracker.count
    metadata.llm_usage = LLMUsage(
        input_tokens=tracker.input_tokens,
        output_tokens=tracker.output_tokens,
        estimated_cost_usd=estimate_llm_cost_usd(
            llm_selector,
            tracker.input_tokens,
            tracker.output_tokens,
        ),
    )
