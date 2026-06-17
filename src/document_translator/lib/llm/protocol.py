from __future__ import annotations

from typing import Protocol


class LLMClient(Protocol):
    def complete(self, system: str, user: str) -> str: ...


class LLMCallTracker:
    def __init__(self) -> None:
        self.count = 0
        self.input_tokens = 0
        self.output_tokens = 0

    def record(self, *, input_tokens: int = 0, output_tokens: int = 0) -> None:
        self.count += 1
        self.input_tokens += max(0, input_tokens)
        self.output_tokens += max(0, output_tokens)

    def increment(self) -> None:
        self.record()
