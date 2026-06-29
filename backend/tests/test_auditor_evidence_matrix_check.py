from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check_auditor_evidence_matrix.sh"
REQUIRED_FILES = (
    Path("docs/auditor-evidence-matrix.md"),
    Path("README.md"),
    Path("docs/production-readiness.md"),
    Path("planning/04-process-tracker.md"),
    Path("Makefile"),
    Path(".github/workflows/ci.yml"),
)


def copy_minimal_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    for relative_path in REQUIRED_FILES:
        target = repo / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative_path, target)
    return repo


def run_checker(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - test runs a fixed local checker path.
        ["/bin/bash", str(CHECKER)],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )


def test_auditor_evidence_matrix_checker_accepts_current_contract(tmp_path: Path) -> None:
    repo = copy_minimal_repo(tmp_path)

    result = run_checker(repo)

    assert result.returncode == 0, result.stderr + result.stdout
    assert "Auditor evidence matrix OK" in result.stdout


def test_auditor_evidence_matrix_checker_rejects_missing_document_context(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    matrix = repo / "docs/auditor-evidence-matrix.md"
    matrix.write_text(
        matrix.read_text(encoding="utf-8").replace(
            "compact document context cards",
            "document UI",
        ),
        encoding="utf-8",
    )

    result = run_checker(repo)

    assert result.returncode != 0
    assert "compact document context cards" in result.stderr + result.stdout


def test_auditor_evidence_matrix_checker_rejects_missing_frontend_format_gate(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    matrix = repo / "docs/auditor-evidence-matrix.md"
    matrix.write_text(
        matrix.read_text(encoding="utf-8").replace(
            "make frontend-format-check",
            "make frontend-style-check",
        ),
        encoding="utf-8",
    )

    result = run_checker(repo)

    assert result.returncode != 0
    assert "matrix missing local gate: make frontend-format-check" in result.stderr + result.stdout


def test_auditor_evidence_matrix_checker_rejects_missing_readme_trace(
    tmp_path: Path,
) -> None:
    repo = copy_minimal_repo(tmp_path)
    readme = repo / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8").replace(
            "visible document/archive scope",
            "document scope",
        ),
        encoding="utf-8",
    )

    result = run_checker(repo)

    assert result.returncode != 0
    assert "README missing document UI phrase" in result.stderr + result.stdout
