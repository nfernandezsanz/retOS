from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check_ci_status.sh"
SHA = "a" * 40
RUN_ID = 123456


def write_fake_curl(
    bin_dir: Path,
    *,
    runs: list[dict[str, Any]] | None = None,
    jobs: list[dict[str, Any]] | None = None,
    artifacts: list[dict[str, Any]] | None = None,
) -> None:
    payload_dir = bin_dir / "payloads"
    payload_dir.mkdir()
    (payload_dir / "runs.json").write_text(
        json.dumps(
            {
                "workflow_runs": (
                    runs
                    if runs is not None
                    else [
                        {
                            "id": RUN_ID,
                            "name": "CI",
                            "head_sha": SHA,
                            "status": "completed",
                            "conclusion": "success",
                            "created_at": "2026-06-29T00:00:00Z",
                            "html_url": "https://github.test/run",
                        }
                    ]
                )
            }
        ),
        encoding="utf-8",
    )
    (payload_dir / "jobs.json").write_text(
        json.dumps(
            {
                "jobs": (
                    jobs
                    if jobs is not None
                    else [
                        {"name": "backend", "status": "completed", "conclusion": "success"},
                        {"name": "frontend", "status": "completed", "conclusion": "success"},
                        {"name": "docker", "status": "completed", "conclusion": "success"},
                        {"name": "audit-evidence", "status": "completed", "conclusion": "success"},
                    ]
                )
            }
        ),
        encoding="utf-8",
    )
    required_artifacts = [
        f"retos-backend-coverage-{SHA}",
        f"retos-visual-audit-{SHA}",
        f"retos-audit-manifest-{SHA}",
        f"retos-audit-handoff-{SHA}",
    ]
    (payload_dir / "artifacts.json").write_text(
        json.dumps(
            {
                "artifacts": (
                    artifacts
                    if artifacts is not None
                    else [
                        {"name": name, "expired": False, "size_in_bytes": 1024}
                        for name in required_artifacts
                    ]
                )
            }
        ),
        encoding="utf-8",
    )
    curl = bin_dir / "curl"
    curl.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                "output=''",
                "url=''",
                'args=("$@")',
                "for ((i=0; i<${#args[@]}; i++)); do",
                "  if [[ \"${args[$i]}\" == '-o' ]]; then",
                '    output="${args[$((i + 1))]}"',
                "  fi",
                '  if [[ "${args[$i]}" == http* ]]; then',
                '    url="${args[$i]}"',
                "  fi",
                "done",
                'if [[ -z "$output" ]]; then',
                "  echo 'missing -o' >&2",
                "  exit 2",
                "fi",
                'if [[ -z "$url" ]]; then',
                "  echo 'missing URL' >&2",
                "  exit 2",
                "fi",
                f"payload_dir={str(payload_dir)!r}",
                'case "$url" in',
                '  */actions/runs/*/jobs?*) cp "$payload_dir/jobs.json" "$output" ;;',
                '  */actions/runs/*/artifacts?*) cp "$payload_dir/artifacts.json" "$output" ;;',
                '  */actions/runs?*) cp "$payload_dir/runs.json" "$output" ;;',
                '  *) echo "unexpected URL: $url" >&2; exit 2 ;;',
                "esac",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    curl.chmod(0o755)


def run_checker(tmp_path: Path, bin_dir: Path) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "RETOS_CI_SHA": SHA,
        "RETOS_GITHUB_REPOSITORY": "owner/repo",
        "GITHUB_API_URL": "https://api.github.test",
    }
    return subprocess.run(  # noqa: S603
        ["/bin/bash", str(CHECKER)],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def test_ci_status_check_passes_with_successful_run_jobs_and_artifacts(
    tmp_path: Path,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_curl(bin_dir)

    result = run_checker(tmp_path, bin_dir)

    assert result.returncode == 0, result.stderr
    assert "CI status OK" in result.stdout
    assert "owner/repo@aaaaaaa" in result.stdout


def test_ci_status_check_fails_when_ci_run_is_missing(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_curl(bin_dir, runs=[])

    result = run_checker(tmp_path, bin_dir)

    assert result.returncode != 0
    assert "no CI workflow run found" in result.stderr


def test_ci_status_check_fails_when_required_job_failed(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_curl(
        bin_dir,
        jobs=[
            {"name": "backend", "status": "completed", "conclusion": "failure"},
            {"name": "frontend", "status": "completed", "conclusion": "success"},
            {"name": "docker", "status": "completed", "conclusion": "success"},
            {"name": "audit-evidence", "status": "completed", "conclusion": "success"},
        ],
    )

    result = run_checker(tmp_path, bin_dir)

    assert result.returncode != 0
    assert "required CI job(s) are not successful" in result.stderr
    assert "backend=completed/failure" in result.stderr


def test_ci_status_check_fails_when_required_artifact_is_missing(
    tmp_path: Path,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_fake_curl(
        bin_dir,
        artifacts=[
            {"name": f"retos-backend-coverage-{SHA}", "expired": False, "size_in_bytes": 1024},
            {"name": f"retos-visual-audit-{SHA}", "expired": False, "size_in_bytes": 1024},
            {"name": f"retos-audit-manifest-{SHA}", "expired": False, "size_in_bytes": 1024},
        ],
    )

    result = run_checker(tmp_path, bin_dir)

    assert result.returncode != 0
    assert "missing required artifact(s)" in result.stderr
    assert f"retos-audit-handoff-{SHA}" in result.stderr
