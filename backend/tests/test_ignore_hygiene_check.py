from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check_ignore_hygiene.sh"
REQUIRED_FILES = (
    Path(".gitignore"),
    Path(".dockerignore"),
    Path("docs/docker.md"),
    Path("docs/operations.md"),
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
    )


def remove_line(path: Path, line: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text(
        "\n".join(existing for existing in lines if existing.strip() != line) + "\n",
        encoding="utf-8",
    )


def test_ignore_hygiene_check_passes_for_current_contract(tmp_path: Path) -> None:
    repo = copy_minimal_repo(tmp_path)

    result = run_checker(repo)

    assert result.returncode == 0, result.stderr
    assert "Ignore hygiene OK" in result.stdout


def test_ignore_hygiene_check_fails_when_gitignore_loses_local_volume_rule(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    remove_line(repo / ".gitignore", "retos_storage/")

    result = run_checker(repo)

    assert result.returncode != 0
    assert ".gitignore missing: retos_storage/" in result.stderr


def test_ignore_hygiene_check_fails_when_dockerignore_loses_docs_exclusion(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    remove_line(repo / ".dockerignore", "docs")

    result = run_checker(repo)

    assert result.returncode != 0
    assert ".dockerignore missing: docs" in result.stderr


def test_ignore_hygiene_check_fails_when_gitignore_loses_backend_coverage_rule(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    remove_line(repo / ".gitignore", "backend/coverage.json")

    result = run_checker(repo)

    assert result.returncode != 0
    assert ".gitignore missing: backend/coverage.json" in result.stderr


def test_ignore_hygiene_check_fails_when_dockerignore_loses_backend_cache_rule(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    remove_line(repo / ".dockerignore", "backend/.pytest_cache")

    result = run_checker(repo)

    assert result.returncode != 0
    assert ".dockerignore missing: backend/.pytest_cache" in result.stderr


def test_ignore_hygiene_check_fails_without_documented_backup_directory(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    operations = repo / "docs/operations.md"
    operations.write_text(
        operations.read_text(encoding="utf-8").replace(
            'backup_dir="backups/', 'backup_dir="retos_backups/'
        ),
        encoding="utf-8",
    )

    result = run_checker(repo)

    assert result.returncode != 0
    assert "local backups under backups/" in result.stderr
