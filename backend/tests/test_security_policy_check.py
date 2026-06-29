from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check_security_policy.sh"
REQUIRED_FILES = (
    Path("SECURITY.md"),
    Path("README.md"),
    Path("docs/operations.md"),
    Path("docs/production-readiness.md"),
    Path("docs/releases/evidence/target-security-review-template.md"),
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


def test_security_policy_check_passes_for_current_contract(tmp_path: Path) -> None:
    repo = copy_minimal_repo(tmp_path)

    result = run_checker(repo)

    assert result.returncode == 0, result.stderr
    assert "Security policy OK" in result.stdout


def test_security_policy_check_fails_when_reporting_heading_is_missing(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    replace_text(repo / "SECURITY.md", "## Reporting", "## Contact")

    result = run_checker(repo)

    assert result.returncode != 0
    assert "SECURITY.md missing ## Reporting" in result.stderr


def test_security_policy_check_fails_when_paid_llm_default_is_removed(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    replace_text(
        repo / "SECURITY.md",
        "Paid LLM calls are disabled by default",
        "External model calls are available",
    )

    result = run_checker(repo)

    assert result.returncode != 0
    assert "SECURITY.md missing security phrase: Paid LLM calls are disabled" in result.stderr


def test_security_policy_check_fails_when_readme_stops_linking_policy(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    replace_text(repo / "README.md", "SECURITY.md", "SECURITY policy")

    result = run_checker(repo)

    assert result.returncode != 0
    assert "README.md must link SECURITY.md" in result.stderr


def test_security_policy_check_fails_when_review_template_loses_auth_section(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    replace_text(
        repo / "docs" / "releases" / "evidence" / "target-security-review-template.md",
        "Auth And Access",
        "Access Review",
    )

    result = run_checker(repo)

    assert result.returncode != 0
    assert (
        "target security review template missing security phrase: Auth And Access" in result.stderr
    )
