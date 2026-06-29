from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check_ci_workflow.sh"
REQUIRED_FILES = (
    Path(".github/workflows/ci.yml"),
    Path("README.md"),
    Path("docs/production-readiness.md"),
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


def replace_text(path: Path, old: str, new: str) -> None:
    content = path.read_text(encoding="utf-8")
    assert old in content
    path.write_text(content.replace(old, new), encoding="utf-8")


def test_ci_workflow_check_passes_for_current_contract(tmp_path: Path) -> None:
    repo = copy_minimal_repo(tmp_path)

    result = run_checker(repo)

    assert result.returncode == 0, result.stderr
    assert "CI workflow OK" in result.stdout


def test_ci_workflow_check_fails_without_root_python_black_gate(tmp_path: Path) -> None:
    repo = copy_minimal_repo(tmp_path)
    replace_text(
        repo / ".github/workflows/ci.yml", "black --check --diff scripts", "echo skip root black"
    )

    result = run_checker(repo)

    assert result.returncode != 0
    assert "ci.yml missing black --check --diff scripts" in result.stderr


def test_ci_workflow_check_fails_without_visual_audit_manifest_artifact(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    replace_text(
        repo / ".github/workflows/ci.yml",
        "frontend/visual-audit/manifest.json",
        "frontend/visual-audit/manifest.local.json",
    )

    result = run_checker(repo)

    assert result.returncode != 0
    assert "ci.yml missing frontend/visual-audit/manifest.json" in result.stderr


def test_ci_workflow_check_fails_without_readme_ci_status_command(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    replace_text(repo / "README.md", "make ci-status-check", "make ci-check")

    result = run_checker(repo)

    assert result.returncode != 0
    assert "README.md missing CI phrase: make ci-status-check" in result.stderr


def test_ci_workflow_check_fails_without_production_ci_health_section(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    replace_text(repo / "docs/production-readiness.md", "CI health", "Pipeline health")

    result = run_checker(repo)

    assert result.returncode != 0
    assert "production readiness missing CI phrase: CI health" in result.stderr
