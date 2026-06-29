from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check_release_notes.sh"
REQUIRED_FILES = (
    Path("CHANGELOG.md"),
    Path("README.md"),
    Path("docs/operations.md"),
    Path("docs/release-process.md"),
    Path("docs/releases/2026.06.28-alpha.1.md"),
)


def copy_minimal_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    for relative in REQUIRED_FILES:
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    return repo


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


def test_release_notes_check_passes_for_current_docs(tmp_path: Path) -> None:
    repo = copy_minimal_repo(tmp_path)

    result = run_checker(repo)

    assert result.returncode == 0, result.stderr
    assert "Release notes OK" in result.stdout


def test_release_notes_check_fails_without_unreleased_section(tmp_path: Path) -> None:
    repo = copy_minimal_repo(tmp_path)
    replace_text(repo / "CHANGELOG.md", "## Unreleased", "## Next")

    result = run_checker(repo)

    assert result.returncode != 0
    assert "CHANGELOG.md must keep an Unreleased section" in result.stderr


def test_release_notes_check_fails_without_visual_audit_release_step(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    replace_text(
        repo / "docs" / "release-process.md",
        "make frontend-visual-audit",
        "make frontend-browser-check",
    )

    result = run_checker(repo)

    assert result.returncode != 0
    assert "docs/release-process.md missing make frontend-visual-audit" in result.stderr


def test_release_notes_check_fails_when_readme_loses_changelog_link(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    replace_text(repo / "README.md", "CHANGELOG.md", "CHANGELOG")

    result = run_checker(repo)

    assert result.returncode != 0
    assert "README.md must link the changelog" in result.stderr


def test_release_notes_check_fails_when_operations_loses_release_process_link(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    replace_text(
        repo / "docs" / "operations.md",
        "docs/release-process.md",
        "docs/releases.md",
    )

    result = run_checker(repo)

    assert result.returncode != 0
    assert "docs/operations.md must point release operators" in result.stderr
