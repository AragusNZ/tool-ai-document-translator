from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from document_translator.config.settings import PipelineConfig
from document_translator.observability import sentry_setup
from document_translator.types import JobStatus


@pytest.fixture(autouse=True)
def reset_sentry_state() -> None:
    sentry_setup._initialized = False
    yield
    sentry_setup._initialized = False


def test_init_sentry_without_dsn() -> None:
    config = PipelineConfig(sentry_dsn=None)
    assert sentry_setup.init_sentry(config) is False


def test_init_sentry_success() -> None:
    mock_sdk = MagicMock()
    config = PipelineConfig(
        sentry_dsn="https://example@o0.ingest.sentry.io/0",
        sentry_environment="test",
        sentry_traces_sample_rate=0.1,
    )
    with patch.dict(sys.modules, {"sentry_sdk": mock_sdk}):
        assert sentry_setup.init_sentry(config) is True
        mock_sdk.init.assert_called_once()
        assert sentry_setup._initialized is True


def test_init_sentry_import_error() -> None:
    config = PipelineConfig(sentry_dsn="https://example@o0.ingest.sentry.io/0")
    import builtins

    real_import = builtins.__import__

    def fake_import(name: str, *args, **kwargs):  # noqa: ANN001
        if name == "sentry_sdk":
            raise ImportError("no sentry")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        assert sentry_setup.init_sentry(config) is False


def test_sentry_translate_transaction_when_not_initialized() -> None:
    with sentry_setup.sentry_translate_transaction("job-1") as transaction:
        assert transaction is None


def test_sentry_translate_transaction_when_initialized() -> None:
    mock_sdk = MagicMock()
    mock_transaction = MagicMock()
    mock_sdk.start_transaction.return_value.__enter__ = MagicMock(return_value=mock_transaction)
    mock_sdk.start_transaction.return_value.__exit__ = MagicMock(return_value=False)

    config = PipelineConfig(sentry_dsn="https://example@o0.ingest.sentry.io/0")
    with patch.dict(sys.modules, {"sentry_sdk": mock_sdk}):
        sentry_setup.init_sentry(config)
        with sentry_setup.sentry_translate_transaction("job-2") as transaction:
            assert transaction is mock_transaction
    mock_transaction.set_tag.assert_called_with("job_id", "job-2")


def test_finish_sentry_transaction_none() -> None:
    sentry_setup.finish_sentry_transaction(None, status=JobStatus.COMPLETED)


def test_finish_sentry_transaction_sets_status() -> None:
    transaction = MagicMock()
    sentry_setup.finish_sentry_transaction(transaction, status=JobStatus.FAILED)
    transaction.set_tag.assert_called_with("status", "failed")
    transaction.set_status.assert_called_with("internal_error")


def test_capture_sentry_exception_when_not_initialized() -> None:
    sentry_setup.capture_sentry_exception(RuntimeError("boom"))
