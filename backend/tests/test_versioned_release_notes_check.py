from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check_versioned_release_notes.sh"
REQUIRED_FILES = (
    Path("README.md"),
    Path("docs/production-readiness.md"),
    Path("docs/releases/README.md"),
    Path("docs/releases/2026.06.28-alpha.1.md"),
)

GIT = shutil.which("git") or "/usr/bin/git"


def copy_minimal_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    for relative in REQUIRED_FILES:
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    initialize_git_history(repo)
    return repo


def initialize_git_history(repo: Path) -> None:
    git(repo, "init")
    git(repo, "config", "user.email", "tests@example.invalid")
    git(repo, "config", "user.name", "Tests")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "fixture")
    commit = git(repo, "rev-parse", "HEAD").stdout.strip()
    release_note = repo / "docs" / "releases" / "2026.06.28-alpha.1.md"
    replace_release_note_local_head(release_note, commit)
    git(repo, "add", str(release_note))
    git(repo, "commit", "-m", "record local evidence")
    recorded_commit = git(repo, "rev-parse", "HEAD").stdout.strip()
    replace_release_note_local_head(release_note, recorded_commit)


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [GIT, *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def replace_release_note_local_head(release_note: Path, commit: str) -> None:
    content = release_note.read_text(encoding="utf-8")
    content = re.sub(
        r"Latest local development evidence commit: `[0-9a-f]{40}`",
        f"Latest local development evidence commit: `{commit}`",
        content,
    )
    release_note.write_text(content, encoding="utf-8")


def run_checker(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        ["/bin/bash", str(CHECKER)],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        env=os.environ,
    )


def replace_text(path: Path, old: str, new: str) -> None:
    content = path.read_text(encoding="utf-8")
    assert old in content
    path.write_text(content.replace(old, new), encoding="utf-8")


def test_versioned_release_notes_check_passes_for_current_contract(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)

    result = run_checker(repo)

    assert result.returncode == 0, result.stderr
    assert "Versioned release notes OK" in result.stdout


def test_versioned_release_notes_check_fails_when_index_loses_cosign(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    replace_text(repo / "docs" / "releases" / "README.md", "Cosign", "Sigstore")

    result = run_checker(repo)

    assert result.returncode != 0
    assert "docs/releases/README.md missing Cosign" in result.stderr


def test_versioned_release_notes_check_fails_when_coverage_is_stale(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    replace_text(
        repo / "docs" / "releases" / "2026.06.28-alpha.1.md",
        "95.43% total coverage",
        "94.00% total coverage",
    )

    result = run_checker(repo)

    assert result.returncode != 0
    assert "must record current backend coverage evidence" in result.stderr


def test_versioned_release_notes_check_fails_when_pytest_count_is_stale(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    replace_text(
        repo / "docs" / "releases" / "2026.06.28-alpha.1.md",
        "make check` passed with 695 tests",
        "make check` passed with 694 tests",
    )

    result = run_checker(repo)

    assert result.returncode != 0
    assert "must record current backend pytest case count" in result.stderr


def test_versioned_release_notes_check_fails_when_local_commit_is_missing(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    replace_release_note_local_head(
        repo / "docs" / "releases" / "2026.06.28-alpha.1.md",
        "f" * 40,
    )

    result = run_checker(repo)

    assert result.returncode != 0
    assert "local development evidence commit must be in the local Git history" in result.stderr
