from __future__ import annotations

from document_translator.lib.llm.pricing import estimate_llm_cost_usd
from document_translator.lib.llm.protocol import LLMCallTracker
from document_translator.lib.llm.tokens import estimate_tokens_from_text
from document_translator.lib.llm.usage import sync_tracker_to_metadata
from document_translator.models import JobMetadata, LLMUsage


def test_llm_call_tracker_aggregates_tokens() -> None:
    tracker = LLMCallTracker()
    tracker.record(input_tokens=100, output_tokens=40)
    tracker.record(input_tokens=50, output_tokens=10)
    assert tracker.count == 2
    assert tracker.input_tokens == 150
    assert tracker.output_tokens == 50


def test_estimate_tokens_from_text() -> None:
    assert estimate_tokens_from_text("") == 0
    assert estimate_tokens_from_text("abcd") == 1
    assert estimate_tokens_from_text("a" * 8) == 2


def test_estimate_llm_cost_usd_known_model() -> None:
    cost = estimate_llm_cost_usd("openai:gpt-4o", input_tokens=1_000_000, output_tokens=0)
    assert cost == 2.5


def test_estimate_llm_cost_usd_unknown_model() -> None:
    assert estimate_llm_cost_usd("unknown:model", 100, 100) is None


def test_sync_tracker_to_metadata() -> None:
    tracker = LLMCallTracker()
    tracker.record(input_tokens=1000, output_tokens=500)
    metadata = JobMetadata(job_id="j1", source_file="doc.txt", model="openai:gpt-4o")
    sync_tracker_to_metadata(metadata, tracker, llm_selector="openai:gpt-4o")
    assert metadata.llm_call_count == 1
    assert metadata.llm_usage == LLMUsage(
        input_tokens=1000,
        output_tokens=500,
        estimated_cost_usd=estimate_llm_cost_usd("openai:gpt-4o", 1000, 500),
    )
