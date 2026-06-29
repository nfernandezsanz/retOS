from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run_script(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [sys.executable, script],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_audit_handoff_report_check_runs_offline() -> None:
    result = run_script("scripts/check_audit_handoff_report.py")

    assert result.returncode == 0, result.stderr
    assert "Audit handoff report OK" in result.stdout


def test_audit_bundle_check_runs_offline() -> None:
    result = run_script("scripts/check_audit_bundle.py")

    assert result.returncode == 0, result.stderr
    assert "Audit bundle OK" in result.stdout
