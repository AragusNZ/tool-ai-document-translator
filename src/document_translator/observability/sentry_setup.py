from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from document_translator.config.settings import PipelineConfig
    from document_translator.types import JobStatus

_initialized = False


def init_sentry(config: PipelineConfig) -> bool:
    global _initialized
    if _initialized or not config.sentry_dsn:
        return False

    try:
        import sentry_sdk
    except ImportError:
        return False

    from document_translator.observability.sentry_scrub import scrub_sentry_event

    init_kwargs: dict[str, Any] = {
        "dsn": config.sentry_dsn,
        "traces_sample_rate": config.sentry_traces_sample_rate,
        "before_send": scrub_sentry_event,
    }
    if config.sentry_environment:
        init_kwargs["environment"] = config.sentry_environment

    sentry_sdk.init(**init_kwargs)
    _initialized = True
    return True


@contextmanager
def sentry_translate_transaction(job_id: str) -> Iterator[Any]:
    try:
        import sentry_sdk
    except ImportError:
        yield None
        return

    if not _initialized:
        yield None
        return

    with sentry_sdk.start_transaction(
        op="pipeline",
        name="document_translator.translate",
    ) as transaction:
        transaction.set_tag("job_id", job_id)
        yield transaction


def finish_sentry_transaction(transaction: Any, *, status: JobStatus) -> None:
    if transaction is None:
        return
    transaction.set_tag("status", status.value)
    transaction.set_status("ok" if status.value.startswith("completed") else "internal_error")


def capture_sentry_exception(exc: BaseException) -> None:
    if not _initialized:
        return
    try:
        import sentry_sdk
    except ImportError:
        return
    sentry_sdk.capture_exception(exc)
