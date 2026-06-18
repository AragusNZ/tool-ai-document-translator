#!/usr/bin/env python3
"""Prepare and publish document-translator releases."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

VERSION_RE = re.compile(r"^version\s*=\s*\"(\d+\.\d+\.\d+)\"\s*$", re.MULTILINE)
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
BUMP_TYPES = frozenset({"patch", "minor", "major"})

README_VERSION_RE = re.compile(
    r"(\*\*Current version:\*\* )\d+\.\d+\.\d+( — see \[CHANGELOG\.md\])"
)
DOCKER_PULL_RE = re.compile(
    r"(docker pull ghcr\.io/aragusnz/tool-ai-document-translator:)\d+\.\d+\.\d+"
)
ROADMAP_VERSION_RE = re.compile(
    r"(Planned improvements beyond the current `)\d+\.\d+\.\d+(` release\.)"
)
UNRELEASED_HEADING = "## [Unreleased]"
VERSION_HEADING_RE = re.compile(r"^## \[(\d+\.\d+\.\d+)\](?: - \d{4}-\d{2}-\d{2})?\s*$", re.MULTILINE)

RELEASE_FILES = (
    "pyproject.toml",
    "CHANGELOG.md",
    "README.md",
    "docs/integration/Docker.md",
    "ROADMAP.md",
)

EMPTY_UNRELEASED = (
    "## [Unreleased]\n\n"
    "### Added\n\n"
    "### Changed\n\n"
    "### Fixed\n\n"
)


class ReleaseError(Exception):
    """Release preparation or publish failed."""


@dataclass(frozen=True)
class ReleasePlan:
    root: Path
    current_version: str
    new_version: str
    release_date: str
    updates: dict[Path, str]


def find_project_root(start: Path | None = None) -> Path:
    path = (start or Path.cwd()).resolve()
    for candidate in (path, *path.parents):
        if (candidate / "pyproject.toml").is_file() and (candidate / "CHANGELOG.md").is_file():
            return candidate
    raise ReleaseError("Could not find project root (need pyproject.toml and CHANGELOG.md)")


def resolve_python_executable(root: Path) -> Path:
    venv_python = root / ".venv" / "bin" / "python"
    if venv_python.is_file():
        return venv_python
    return Path(sys.executable)


def read_version(pyproject_path: Path) -> str:
    content = pyproject_path.read_text(encoding="utf-8")
    match = VERSION_RE.search(content)
    if not match:
        raise ReleaseError(f"No version found in {pyproject_path}")
    return match.group(1)


def parse_version(version: str) -> tuple[int, int, int]:
    if not SEMVER_RE.match(version):
        raise ReleaseError(f"Invalid semver: {version!r}")
    major, minor, patch = (int(part) for part in version.split("."))
    return major, minor, patch


def bump_version(current: str, bump: str) -> str:
    if SEMVER_RE.match(bump):
        return bump
    if bump not in BUMP_TYPES:
        raise ReleaseError(f"Expected patch, minor, major, or X.Y.Z; got {bump!r}")
    major, minor, patch = parse_version(current)
    if bump == "patch":
        patch += 1
    elif bump == "minor":
        minor += 1
        patch = 0
    else:
        major += 1
        minor = 0
        patch = 0
    return f"{major}.{minor}.{patch}"


def version_gt(left: str, right: str) -> bool:
    return parse_version(left) > parse_version(right)


def unreleased_has_content(changelog: str) -> bool:
    if UNRELEASED_HEADING not in changelog:
        return False
    _, rest = changelog.split(UNRELEASED_HEADING, 1)
    next_heading = re.search(r"\n## \[", rest)
    body = rest[: next_heading.start()] if next_heading else rest
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            return True
    return False


def finalize_changelog(changelog: str, new_version: str, release_date: str) -> str:
    if UNRELEASED_HEADING not in changelog:
        raise ReleaseError("CHANGELOG.md is missing ## [Unreleased]")
    if not unreleased_has_content(changelog):
        raise ReleaseError("CHANGELOG.md [Unreleased] has no bullet entries")

    preamble, rest = changelog.split(UNRELEASED_HEADING, 1)
    next_heading = re.search(r"\n## \[", rest)
    if next_heading:
        unreleased_body = rest[: next_heading.start()]
        remainder = rest[next_heading.start() + 1 :]
    else:
        unreleased_body = rest
        remainder = ""

    versioned = f"## [{new_version}] - {release_date}{unreleased_body}"
    return preamble + EMPTY_UNRELEASED + versioned + remainder


def update_pyproject_version(content: str, new_version: str) -> str:
    updated, count = VERSION_RE.subn(f'version = "{new_version}"', content, count=1)
    if count != 1:
        raise ReleaseError("Failed to update version in pyproject.toml")
    return updated


def update_readme_version(content: str, new_version: str) -> str:
    updated, count = README_VERSION_RE.subn(
        rf"\g<1>{new_version}\2",
        content,
        count=1,
    )
    if count != 1:
        raise ReleaseError("Failed to update current version line in README.md")
    return updated


def update_docker_md(content: str, new_version: str) -> str:
    updated, count = DOCKER_PULL_RE.subn(rf"\g<1>{new_version}", content, count=1)
    if count != 1:
        raise ReleaseError("Failed to update docker pull example in docs/integration/Docker.md")
    return updated


def update_roadmap(content: str, new_version: str) -> str:
    updated, count = ROADMAP_VERSION_RE.subn(rf"\g<1>{new_version}\2", content, count=1)
    if count != 1:
        raise ReleaseError("Failed to update version line in ROADMAP.md")
    return updated


def changelog_latest_version(changelog: str) -> str | None:
    for match in VERSION_HEADING_RE.finditer(changelog):
        version = match.group(1)
        if version != "Unreleased":
            return version
    return None


def assert_release_baseline(root: Path) -> None:
    current = read_version(root / "pyproject.toml")
    latest = changelog_latest_version((root / "CHANGELOG.md").read_text(encoding="utf-8"))
    if latest is not None and current != latest:
        raise ReleaseError(
            "pyproject.toml version "
            f"{current!r} does not match latest CHANGELOG release {latest!r}; sync before releasing"
        )


def build_release_plan(
    root: Path,
    bump: str,
    *,
    release_date: str | None = None,
) -> ReleasePlan:
    current = read_version(root / "pyproject.toml")
    new_version = bump_version(current, bump)
    if not version_gt(new_version, current):
        raise ReleaseError(f"New version {new_version} must be greater than current {current}")

    when = release_date or date.today().isoformat()
    changelog_path = root / "CHANGELOG.md"
    changelog = changelog_path.read_text(encoding="utf-8")

    updates: dict[Path, str] = {
        root / "pyproject.toml": update_pyproject_version(
            (root / "pyproject.toml").read_text(encoding="utf-8"),
            new_version,
        ),
        changelog_path: finalize_changelog(changelog, new_version, when),
        root / "README.md": update_readme_version(
            (root / "README.md").read_text(encoding="utf-8"),
            new_version,
        ),
        root / "docs/integration/Docker.md": update_docker_md(
            (root / "docs/integration/Docker.md").read_text(encoding="utf-8"),
            new_version,
        ),
        root / "ROADMAP.md": update_roadmap(
            (root / "ROADMAP.md").read_text(encoding="utf-8"),
            new_version,
        ),
    }
    return ReleasePlan(
        root=root,
        current_version=current,
        new_version=new_version,
        release_date=when,
        updates=updates,
    )


def apply_release_plan(plan: ReleasePlan) -> None:
    for path, content in plan.updates.items():
        path.write_text(content, encoding="utf-8")


def run_git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=check,
        capture_output=True,
        text=True,
    )


def assert_clean_worktree(root: Path) -> None:
    result = run_git(root, "status", "--porcelain")
    if result.stdout.strip():
        raise ReleaseError("Working tree is not clean; commit or stash changes before releasing")


def assert_on_branch(root: Path, branch: str) -> None:
    result = run_git(root, "rev-parse", "--abbrev-ref", "HEAD")
    current = result.stdout.strip()
    if current != branch:
        raise ReleaseError(f"Expected branch {branch!r}, currently on {current!r}")


def tag_exists(root: Path, tag: str, remote: str | None = None) -> bool:
    if remote is None:
        result = run_git(root, "rev-parse", "--verify", tag, check=False)
        return result.returncode == 0
    result = run_git(root, "ls-remote", "--tags", remote, f"refs/tags/{tag}", check=False)
    return result.returncode == 0 and bool(result.stdout.strip())


def assert_versions_consistent(root: Path, version: str) -> None:
    pyproject_version = read_version(root / "pyproject.toml")
    if pyproject_version != version:
        raise ReleaseError(
            f"pyproject.toml version {pyproject_version!r} does not match release {version!r}"
        )
    changelog_version = changelog_latest_version((root / "CHANGELOG.md").read_text(encoding="utf-8"))
    if changelog_version != version:
        raise ReleaseError(
            f"CHANGELOG.md latest release {changelog_version!r} does not match release {version!r}"
        )


def print_plan_summary(plan: ReleasePlan, *, verbose: bool = False) -> None:
    print(f"Release plan: {plan.current_version} -> {plan.new_version} ({plan.release_date})")
    for path in sorted(plan.updates):
        rel = path.relative_to(plan.root)
        print(f"  update {rel}")
    if verbose:
        for path in sorted(plan.updates):
            rel = path.relative_to(plan.root)
            print(f"\n--- {rel} ---")
            print(plan.updates[path])


def run_pytest_gate(root: Path, *, force: bool) -> None:
    python = resolve_python_executable(root)
    result = subprocess.run(
        [
            str(python),
            "-m",
            "pytest",
            '-m',
            "not integration",
            "--cov=document_translator",
            "--cov-report=term-missing",
            "--cov-fail-under=85",
            "-q",
        ],
        cwd=root,
    )
    if result.returncode == 0:
        return
    if force:
        print("pytest failed; continuing because --yes was provided", file=sys.stderr)
        return
    if python == Path(sys.executable) and not (root / ".venv" / "bin" / "python").is_file():
        raise ReleaseError('pytest failed; install dev deps with: pip install -e ".[dev]"')
    raise ReleaseError("pytest failed; fix tests or pass --yes to continue anyway")


def publish_release(plan: ReleasePlan, *, branch: str, force: bool) -> None:
    tag = f"v{plan.new_version}"
    assert_versions_consistent(plan.root, plan.new_version)
    if tag_exists(plan.root, tag):
        raise ReleaseError(f"Tag {tag} already exists locally")
    if tag_exists(plan.root, tag, "origin"):
        raise ReleaseError(f"Tag {tag} already exists on origin")

    run_pytest_gate(plan.root, force=force)
    run_git(plan.root, "add", *RELEASE_FILES)
    run_git(plan.root, "commit", "-m", f"Release {tag}")
    run_git(plan.root, "tag", "-a", tag, "-m", f"Release {tag}")
    run_git(plan.root, "push", "origin", branch)
    run_git(plan.root, "push", "origin", tag)

    print(f"\nPublished {tag}.")
    print("GitHub Actions will run tests, create the GitHub Release, and publish Docker images.")


def prompt_continue(plan: ReleasePlan) -> bool:
    try:
        answer = input(f"Release v{plan.new_version} prepared. Continue with commit, tag, and push? [y/N] ")
    except EOFError:
        return False
    return answer.strip().lower() in {"y", "yes"}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare and publish document-translator releases")
    parser.add_argument(
        "bump",
        help="patch, minor, major, or explicit X.Y.Z version",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print planned changes without writing files",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="print full planned file contents in dry-run mode",
    )
    parser.add_argument(
        "--no-publish",
        action="store_true",
        help="prepare files only; never prompt to commit, tag, or push",
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="skip confirmation prompt and publish automatically",
    )
    parser.add_argument(
        "--branch",
        default="main",
        help="branch to push (default: main)",
    )
    parser.add_argument(
        "--date",
        dest="release_date",
        help="release date YYYY-MM-DD (default: today)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        root = find_project_root()
        run_git(root, "rev-parse", "--is-inside-work-tree")
    except (ReleaseError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    try:
        if not args.dry_run:
            assert_clean_worktree(root)
            assert_on_branch(root, args.branch)
        assert_release_baseline(root)
        plan = build_release_plan(root, args.bump, release_date=args.release_date)
    except ReleaseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print_plan_summary(plan, verbose=args.verbose and args.dry_run)

    if args.dry_run:
        print("\nDry run complete; no files changed.")
        return 0

    try:
        apply_release_plan(plan)
    except ReleaseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"\nPrepared release v{plan.new_version}.")

    if args.no_publish:
        print("Publish skipped (--no-publish). Review changes, then commit and tag manually.")
        return 0

    should_publish = args.yes or prompt_continue(plan)
    if not should_publish:
        print("Publish skipped. Review changes, then commit and tag manually.")
        return 0

    try:
        publish_release(plan, branch=args.branch, force=args.yes)
    except (ReleaseError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
