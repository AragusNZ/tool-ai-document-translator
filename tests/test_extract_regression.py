from __future__ import annotations

import importlib.util

import pytest

from tests.extract_golden import (
    FIXTURES_DIR,
    extract_for_golden,
    normalized_text_hash,
    should_update_golden,
    update_manifest_hashes,
    write_manifest,
)
from tools.extract_eval.golden import GoldenCase, load_manifest


def _liteparse_installed() -> bool:
    return importlib.util.find_spec("liteparse") is not None


def _cases_for_backend(backend: str) -> list[GoldenCase]:
    return [case for case in load_manifest() if case.backend == backend]


def _case_id(case: GoldenCase) -> str:
    return f"{case.backend}:{case.file}"


@pytest.fixture(scope="session")
def golden_cases() -> list[GoldenCase]:
    return load_manifest()


@pytest.mark.parametrize(
    "case",
    _cases_for_backend("pymupdf"),
    ids=_case_id,
)
def test_pymupdf_golden_extraction(case: GoldenCase) -> None:
    path = FIXTURES_DIR / case.file
    assert path.exists(), f"Missing fixture PDF: {path}"

    text = extract_for_golden(case, path)
    actual_hash = normalized_text_hash(text)
    assert len(text.strip()) >= case.min_chars

    if should_update_golden():
        pytest.skip("UPDATE_GOLDEN handled in session finalizer")

    assert actual_hash == case.normalized_text_sha256, (
        f"Golden hash mismatch for {case.file} ({case.backend}). "
        "Re-run with UPDATE_GOLDEN=1 pytest tests/test_extract_regression.py to refresh."
    )


@pytest.mark.requires_liteparse
@pytest.mark.parametrize(
    "case",
    [c for c in _cases_for_backend("liteparse") if c.requires_liteparse],
    ids=_case_id,
)
def test_liteparse_golden_extraction(case: GoldenCase) -> None:
    if not _liteparse_installed():
        pytest.skip("liteparse not installed")

    path = FIXTURES_DIR / case.file
    text = extract_for_golden(case, path)
    actual_hash = normalized_text_hash(text)
    assert len(text.strip()) >= case.min_chars

    if should_update_golden():
        pytest.skip("UPDATE_GOLDEN handled in session finalizer")

    assert actual_hash == case.normalized_text_sha256


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if not should_update_golden():
        return
    cases = load_manifest()
    updated = update_manifest_hashes(cases)
    write_manifest(updated)
    terminal = session.config.pluginmanager.get_plugin("terminalreporter")
    if terminal is not None:
        terminal.write_line(f"Updated golden manifest: {len(updated)} cases")
