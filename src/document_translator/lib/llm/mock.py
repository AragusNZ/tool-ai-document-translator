from __future__ import annotations

from document_translator.lib.llm.protocol import LLMCallTracker
from document_translator.lib.llm.tokens import estimate_tokens_from_text


class MockLLMClient:
    """Deterministic mock for tests. Returns prefixed user content."""

    def __init__(self, *, prefix: str = "[EN] ", tracker: LLMCallTracker | None = None) -> None:
        self.prefix = prefix
        self.tracker = tracker or LLMCallTracker()
        self._responses: dict[str, str] = {}
        self.calls: list[tuple[str, str]] = []

    def set_response(self, key: str, response: str) -> None:
        self._responses[key] = response

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        for key, response in self._responses.items():
            if key in user:
                result = response
                self.tracker.record(
                    input_tokens=estimate_tokens_from_text(system + user),
                    output_tokens=estimate_tokens_from_text(result),
                )
                return result
        if "semantic" in system.lower() or "equivalent" in system.lower():
            result = '{"equivalent": true, "severity": "low", "explanation": "mock equivalent"}'
        elif "adjudicate" in system.lower() or "choose" in system.lower():
            result = user.split("Variant")[1].split("\n")[0] if "Variant" in user else self.prefix + user[:80]
        elif "language" in system.lower():
            result = "es"
        else:
            result = self.prefix + user
        self.tracker.record(
            input_tokens=estimate_tokens_from_text(system + user),
            output_tokens=estimate_tokens_from_text(result),
        )
        return result
