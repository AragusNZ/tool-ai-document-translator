from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
RELEASE_SCRIPT = ROOT / "scripts" / "release.py"


def load_release_module():
    spec = importlib.util.spec_from_file_location("release_script", RELEASE_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


release = load_release_module()


MINIMAL_CHANGELOG = """\
# Changelog

## [Unreleased]

### Added

- New feature bullet

### Fixed

- Bug fix bullet

## [0.1.0] - 2026-06-17

### Added

- Initial release
"""

MINIMAL_PYPROJECT = """\
[project]
name = "document-translator"
version = "0.1.0"
"""

MINIMAL_README = """\
# Document Translator

**Current version:** 0.1.0 — see [CHANGELOG.md](CHANGELOG.md) for release history.
"""

MINIMAL_DOCKER = """\
Pull a release:

```bash
docker pull ghcr.io/aragusnz/tool-ai-document-translator:0.1.0
```
"""

MINIMAL_ROADMAP = """\
# Roadmap

Planned improvements beyond the current `0.1.0` release. Not committed to a timeline.
"""


@pytest.fixture
def release_tree(tmp_path: Path) -> Path:
    (tmp_path / "docs" / "integration").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text(MINIMAL_PYPROJECT, encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text(MINIMAL_CHANGELOG, encoding="utf-8")
    (tmp_path / "README.md").write_text(MINIMAL_README, encoding="utf-8")
    (tmp_path / "docs" / "integration" / "Docker.md").write_text(MINIMAL_DOCKER, encoding="utf-8")
    (tmp_path / "ROADMAP.md").write_text(MINIMAL_ROADMAP, encoding="utf-8")
    subprocess.run(["git", "init", "-b", "main"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=test@example.com",
            "-c",
            "user.name=Test",
            "commit",
            "-m",
            "init",
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    return tmp_path


def test_bump_version_levels() -> None:
    assert release.bump_version("0.1.0", "patch") == "0.1.1"
    assert release.bump_version("0.1.0", "minor") == "0.2.0"
    assert release.bump_version("0.1.0", "major") == "1.0.0"
    assert release.bump_version("0.1.0", "0.3.4") == "0.3.4"


def test_resolve_python_executable_prefers_project_venv(release_tree: Path) -> None:
    venv_bin = release_tree / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    venv_python = venv_bin / "python"
    venv_python.write_text("#!/bin/sh\n", encoding="utf-8")
    assert release.resolve_python_executable(release_tree) == venv_python


def test_resolve_python_executable_falls_back_to_current_interpreter(release_tree: Path) -> None:
    assert release.resolve_python_executable(release_tree) == Path(sys.executable)


def test_bump_version_rejects_downgrade_target(release_tree: Path) -> None:
    with pytest.raises(release.ReleaseError, match="greater than current"):
        release.build_release_plan(release_tree, "0.1.0")


def test_finalize_changelog_moves_unreleased_content() -> None:
    updated = release.finalize_changelog(MINIMAL_CHANGELOG, "0.2.0", "2026-06-18")
    assert updated.startswith("# Changelog\n\n## [Unreleased]\n\n### Added\n\n### Changed\n\n### Fixed\n\n")
    assert "## [0.2.0] - 2026-06-18" in updated
    assert "- New feature bullet" in updated
    assert "- Bug fix bullet" in updated
    assert "## [0.1.0] - 2026-06-17" in updated


def test_finalize_changelog_rejects_empty_unreleased() -> None:
    empty = "# Changelog\n\n## [Unreleased]\n\n### Added\n\n## [0.1.0] - 2026-06-17\n"
    with pytest.raises(release.ReleaseError, match="no bullet entries"):
        release.finalize_changelog(empty, "0.2.0", "2026-06-18")


def test_finalize_changelog_supports_first_release_without_prior_heading() -> None:
    first = """\
# Changelog

## [Unreleased]

### Added

- Initial public release

"""
    updated = release.finalize_changelog(first, "0.2.0", "2026-06-18")
    assert "## [0.2.0] - 2026-06-18" in updated
    assert "- Initial public release" in updated
    assert "## [Unreleased]" in updated


def test_assert_release_baseline_rejects_mismatch(release_tree: Path) -> None:
    (release_tree / "pyproject.toml").write_text(
        MINIMAL_PYPROJECT.replace("0.1.0", "0.0.0"),
        encoding="utf-8",
    )
    with pytest.raises(release.ReleaseError, match="does not match latest CHANGELOG release"):
        release.assert_release_baseline(release_tree)


def test_build_release_plan_updates_all_files(release_tree: Path) -> None:
    plan = release.build_release_plan(release_tree, "minor", release_date="2026-06-18")
    assert plan.current_version == "0.1.0"
    assert plan.new_version == "0.2.0"
    assert 'version = "0.2.0"' in plan.updates[release_tree / "pyproject.toml"]
    assert "**Current version:** 0.2.0" in plan.updates[release_tree / "README.md"]
    assert "tool-ai-document-translator:0.2.0" in plan.updates[release_tree / "docs" / "integration" / "Docker.md"]
    assert "current `0.2.0` release" in plan.updates[release_tree / "ROADMAP.md"]


def test_apply_release_plan_writes_files(release_tree: Path) -> None:
    plan = release.build_release_plan(release_tree, "patch", release_date="2026-06-18")
    release.apply_release_plan(plan)
    assert release.read_version(release_tree / "pyproject.toml") == "0.1.1"
    changelog = (release_tree / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "## [0.1.1] - 2026-06-18" in changelog
    assert release.changelog_latest_version(changelog) == "0.1.1"


def test_dry_run_does_not_write_files(release_tree: Path) -> None:
    before = {
        path.name: path.read_text(encoding="utf-8")
        for path in release_tree.iterdir()
        if path.is_file()
    }
    result = subprocess.run(
        [sys.executable, str(RELEASE_SCRIPT), "patch", "--dry-run"],
        cwd=release_tree,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Dry run complete" in result.stdout
    after = {
        path.name: path.read_text(encoding="utf-8")
        for path in release_tree.iterdir()
        if path.is_file()
    }
    assert before == after


def test_main_rejects_dirty_worktree(release_tree: Path) -> None:
    (release_tree / "README.md").write_text("dirty", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(RELEASE_SCRIPT), "patch", "--no-publish"],
        cwd=release_tree,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "Working tree is not clean" in result.stderr


def test_publish_release_runs_git_and_pytest(release_tree: Path) -> None:
    plan = release.build_release_plan(release_tree, "patch", release_date="2026-06-18")
    release.apply_release_plan(plan)

    with (
        patch.object(release, "run_pytest_gate") as pytest_gate,
        patch.object(release, "run_git") as run_git,
        patch.object(release, "tag_exists", return_value=False),
    ):
        release.publish_release(plan, branch="main", force=False)

    pytest_gate.assert_called_once_with(release_tree, force=False)
    run_git.assert_any_call(release_tree, "add", *release.RELEASE_FILES)
    run_git.assert_any_call(release_tree, "commit", "-m", "Release v0.1.1")
    run_git.assert_any_call(release_tree, "tag", "-a", "v0.1.1", "-m", "Release v0.1.1")
    run_git.assert_any_call(release_tree, "push", "origin", "main")
    run_git.assert_any_call(release_tree, "push", "origin", "v0.1.1")


def test_publish_release_aborts_when_tag_exists(release_tree: Path) -> None:
    plan = release.build_release_plan(release_tree, "patch", release_date="2026-06-18")
    release.apply_release_plan(plan)

    with (
        patch.object(release, "tag_exists", side_effect=[False, True]),
        pytest.raises(release.ReleaseError, match="already exists on origin"),
    ):
        release.publish_release(plan, branch="main", force=False)


def test_tag_exists_remote_ignores_empty_ls_remote_output(release_tree: Path) -> None:
    empty = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    with patch.object(release, "run_git", return_value=empty):
        assert not release.tag_exists(release_tree, "v0.3.0", "origin")


def test_tag_exists_remote_detects_matching_ref(release_tree: Path) -> None:
    found = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout="abc123\trefs/tags/v0.3.0\n",
        stderr="",
    )
    with patch.object(release, "run_git", return_value=found) as run_git:
        assert release.tag_exists(release_tree, "v0.3.0", "origin")
    run_git.assert_called_once_with(release_tree, "ls-remote", "--tags", "origin", "refs/tags/v0.3.0", check=False)


def test_assert_versions_consistent(release_tree: Path) -> None:
    plan = release.build_release_plan(release_tree, "patch", release_date="2026-06-18")
    release.apply_release_plan(plan)
    release.assert_versions_consistent(release_tree, "0.1.1")

    with pytest.raises(release.ReleaseError, match="does not match release"):
        release.assert_versions_consistent(release_tree, "9.9.9")
