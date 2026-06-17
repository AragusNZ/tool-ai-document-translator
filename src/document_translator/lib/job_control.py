from __future__ import annotations

import signal
import threading
import time

from document_translator.errors import JobCancelledError, JobTimeoutError
from document_translator.types import PipelineStage

_cancel_event = threading.Event()
_handlers_installed = False


def reset_job_control() -> None:
    _cancel_event.clear()


def request_job_cancel() -> None:
    _cancel_event.set()


def is_job_cancelled() -> bool:
    return _cancel_event.is_set()


def install_job_signal_handlers() -> None:
    global _handlers_installed
    if _handlers_installed:
        return

    def _handle_signal(signum: int, frame: object) -> None:  # noqa: ARG001
        _cancel_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _handle_signal)
        except (ValueError, OSError):
            pass
    _handlers_installed = True


class JobDeadline:
    def __init__(self, timeout_seconds: float | None, *, started: float | None = None) -> None:
        self.timeout_seconds = timeout_seconds
        self.started = started if started is not None else time.monotonic()

    def check(self, stage: PipelineStage) -> None:
        if is_job_cancelled():
            raise JobCancelledError(stage=stage)
        if self.timeout_seconds is not None and time.monotonic() - self.started >= self.timeout_seconds:
            raise JobTimeoutError(stage=stage, timeout_seconds=self.timeout_seconds)

    def elapsed(self) -> float:
        return time.monotonic() - self.started
