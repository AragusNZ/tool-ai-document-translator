from document_translator.errors import (
    ChunkCountMismatchError,
    ConfigurationError,
    IssueCode,
    PipelineError,
    UnsupportedFormatError,
)
from document_translator.types import PipelineStage


def test_unsupported_format_error() -> None:
    err = UnsupportedFormatError(".xyz")
    assert err.code == IssueCode.UNSUPPORTED_FORMAT
    assert err.stage == PipelineStage.EXTRACTING
    assert err.scope["suffix"] == ".xyz"


def test_chunk_count_mismatch_error() -> None:
    err = ChunkCountMismatchError(3, 5)
    assert err.code == IssueCode.CHUNK_COUNT_MISMATCH
    assert err.scope["pass1"] == "3"
    assert err.scope["pass2"] == "5"


def test_configuration_error() -> None:
    err = ConfigurationError("bad config")
    assert err.code == IssueCode.CONFIGURATION_ERROR
    assert str(err) == "bad config"


def test_pipeline_error_with_cause() -> None:
    cause = ValueError("root cause")
    err = PipelineError(
        "failed",
        code=IssueCode.PIPELINE_FAILED,
        stage=PipelineStage.TRANSLATING,
        cause=cause,
        scope={"chunk_index": "0"},
    )
    assert err.cause is cause
    assert err.scope["chunk_index"] == "0"
