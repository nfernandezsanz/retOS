from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check_process_tracker.py"


def copy_tracker(tmp_path: Path) -> Path:
    tracker = tmp_path / "planning" / "04-process-tracker.md"
    tracker.parent.mkdir(parents=True)
    tracker.write_text(
        (ROOT / "planning" / "04-process-tracker.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return tracker


def run_checker(tracker: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [sys.executable, str(CHECKER), "--tracker", str(tracker)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def replace_text(path: Path, old: str, new: str) -> None:
    content = path.read_text(encoding="utf-8")
    assert old in content
    path.write_text(content.replace(old, new), encoding="utf-8")


def test_process_tracker_check_accepts_current_contract(tmp_path: Path) -> None:
    tracker = copy_tracker(tmp_path)

    result = run_checker(tracker)

    assert result.returncode == 0, result.stderr
    assert "Process tracker OK" in result.stdout


def test_process_tracker_check_rejects_missing_release_blocker(
    tmp_path: Path,
) -> None:
    tracker = copy_tracker(tmp_path)
    replace_text(
        tracker,
        "Final release promotion still requires",
        "Release promotion still requires",
    )

    result = run_checker(tracker)

    assert result.returncode != 0
    assert "phase 6 must keep external promotion blockers visible" in result.stderr


def test_process_tracker_check_rejects_missing_visual_audit_evidence(
    tmp_path: Path,
) -> None:
    tracker = copy_tracker(tmp_path)
    replace_text(tracker, "frontend-visual-audit", "frontend-screenshot")

    result = run_checker(tracker)

    assert result.returncode != 0
    assert "phase 4 must keep tooltip and visual audit evidence visible" in result.stderr
