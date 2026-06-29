from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check_operations_runbook.sh"
REQUIRED_FILES = (
    Path("docs/operations.md"),
    Path("docs/production-readiness.md"),
    Path("docs/releases/evidence/production-promotion-template.md"),
    Path("docs/releases/evidence/backup-restore-drill-template.md"),
    Path("docs/releases/evidence/target-security-review-template.md"),
    Path("docs/releases/evidence/calibration-scope-decision-template.md"),
    Path(".gitignore"),
    Path(".dockerignore"),
    Path("backend/scripts/smoke_api.py"),
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


def test_operations_runbook_check_passes_for_current_contract(tmp_path: Path) -> None:
    repo = copy_minimal_repo(tmp_path)

    result = run_checker(repo)

    assert result.returncode == 0, result.stderr
    assert "Operations runbook OK" in result.stdout


def test_operations_runbook_check_fails_when_rollback_heading_is_missing(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    replace_text(repo / "docs" / "operations.md", "## Rollback Notes", "## Revert Notes")

    result = run_checker(repo)

    assert result.returncode != 0
    assert "docs/operations.md missing ## Rollback Notes" in result.stderr


def test_operations_runbook_check_fails_when_backups_are_not_ignored(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    replace_text(repo / ".dockerignore", "backups", "backup-output")

    result = run_checker(repo)

    assert result.returncode != 0
    assert ".dockerignore must exclude local backups" in result.stderr


def test_operations_runbook_check_fails_when_api_smoke_loses_audit_export(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    replace_text(repo / "backend" / "scripts" / "smoke_api.py", "/audit/export", "/audit/logs")

    result = run_checker(repo)

    assert result.returncode != 0
    assert "API smoke must exercise audit export" in result.stderr


def test_operations_runbook_check_fails_when_drill_template_loses_api_smoke(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    replace_text(
        repo / "docs" / "releases" / "evidence" / "backup-restore-drill-template.md",
        "`make api-smoke` output",
        "`make smoke-api` output",
    )

    result = run_checker(repo)

    assert result.returncode != 0
    assert (
        "backup/restore drill template missing evidence field: `make api-smoke` output"
        in result.stderr
    )
