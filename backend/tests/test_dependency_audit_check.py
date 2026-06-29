from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check_dependency_audit.sh"


def write_minimal_repo(tmp_path: Path) -> tuple[Path, Path, Path]:
    repo = tmp_path / "repo"
    bin_dir = tmp_path / "bin"
    log_path = tmp_path / "audit.log"
    (repo / "backend").mkdir(parents=True)
    (repo / "frontend").mkdir()
    bin_dir.mkdir()
    (repo / "backend" / "requirements.txt").write_text("fastapi==0.1\n", encoding="utf-8")
    return repo, bin_dir, log_path


def write_fake_python(bin_dir: Path, log_path: Path, *, fail: bool = False) -> Path:
    python = bin_dir / "python-audit"
    python.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                f"echo python:$PWD:$* >> {str(log_path)!r}",
                'if [[ "$*" != "-m pip_audit -r backend/requirements.txt" ]]; then',
                "  echo 'unexpected python audit command' >&2",
                "  exit 2",
                "fi",
                "exit 7" if fail else "exit 0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    python.chmod(0o755)
    return python


def write_fake_npm(bin_dir: Path, log_path: Path, *, fail: bool = False) -> None:
    npm = bin_dir / "npm"
    npm.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                f"echo npm:$PWD:$* >> {str(log_path)!r}",
                'if [[ "$*" != "audit --audit-level=high" ]]; then',
                "  echo 'unexpected npm audit command' >&2",
                "  exit 2",
                "fi",
                'case "$PWD" in',
                "  */frontend) ;;",
                "  *) echo 'npm audit must run in frontend' >&2; exit 2 ;;",
                "esac",
                "exit 9" if fail else "exit 0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    npm.chmod(0o755)


def run_checker(
    repo: Path,
    bin_dir: Path,
    python: Path,
) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "BACKEND_PYTHON": str(python),
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
    }
    return subprocess.run(  # noqa: S603
        ["/bin/bash", str(CHECKER)],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def test_dependency_audit_check_runs_python_and_frontend_audits(
    tmp_path: Path,
) -> None:
    repo, bin_dir, log_path = write_minimal_repo(tmp_path)
    python = write_fake_python(bin_dir, log_path)
    write_fake_npm(bin_dir, log_path)

    result = run_checker(repo, bin_dir, python)

    assert result.returncode == 0, result.stderr
    log = log_path.read_text(encoding="utf-8")
    assert "python:" in log
    assert "npm:" in log
    assert "-m pip_audit -r backend/requirements.txt" in log
    assert "audit --audit-level=high" in log


def test_dependency_audit_check_stops_when_python_audit_fails(
    tmp_path: Path,
) -> None:
    repo, bin_dir, log_path = write_minimal_repo(tmp_path)
    python = write_fake_python(bin_dir, log_path, fail=True)
    write_fake_npm(bin_dir, log_path)

    result = run_checker(repo, bin_dir, python)

    assert result.returncode == 7
    log = log_path.read_text(encoding="utf-8")
    assert "python:" in log
    assert "npm:" not in log


def test_dependency_audit_check_fails_when_npm_audit_fails(tmp_path: Path) -> None:
    repo, bin_dir, log_path = write_minimal_repo(tmp_path)
    python = write_fake_python(bin_dir, log_path)
    write_fake_npm(bin_dir, log_path, fail=True)

    result = run_checker(repo, bin_dir, python)

    assert result.returncode == 9
    log = log_path.read_text(encoding="utf-8")
    assert "python:" in log
    assert "npm:" in log
