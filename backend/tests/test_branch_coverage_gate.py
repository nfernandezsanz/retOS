import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest


def load_branch_coverage_gate() -> ModuleType:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "check_branch_coverage.py"
    spec = importlib.util.spec_from_file_location("check_branch_coverage", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load branch coverage gate from {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_coverage_report(
    path: Path,
    *,
    branch_coverage: bool = True,
    covered_branches: int = 90,
    num_branches: int = 100,
) -> Path:
    path.write_text(
        json.dumps(
            {
                "meta": {"branch_coverage": branch_coverage},
                "totals": {
                    "covered_branches": covered_branches,
                    "num_branches": num_branches,
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def test_branch_coverage_gate_accepts_reports_at_threshold(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    gate = load_branch_coverage_gate()
    report_path = write_coverage_report(tmp_path / "coverage.json")

    exit_code = gate.run(coverage_json=report_path, fail_under=90.0)

    assert exit_code == 0
    assert "Backend branch coverage: 90.00% (90/100 branches)" in capsys.readouterr().out


def test_branch_coverage_gate_rejects_reports_below_threshold(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    gate = load_branch_coverage_gate()
    report_path = write_coverage_report(
        tmp_path / "coverage.json",
        covered_branches=89,
        num_branches=100,
    )

    exit_code = gate.run(coverage_json=report_path, fail_under=90.0)

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "Backend branch coverage: 89.00% (89/100 branches)" in output
    assert "below the required threshold" in output


def test_branch_coverage_gate_compares_displayed_rounded_percentage(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    gate = load_branch_coverage_gate()
    report_path = write_coverage_report(
        tmp_path / "coverage.json",
        covered_branches=1189,
        num_branches=1370,
    )

    exit_code = gate.run(coverage_json=report_path, fail_under=86.79)

    assert exit_code == 0
    assert "Backend branch coverage: 86.79% (1189/1370 branches)" in capsys.readouterr().out


def test_branch_coverage_gate_requires_branch_coverage_report(tmp_path: Path) -> None:
    gate = load_branch_coverage_gate()
    report_path = write_coverage_report(
        tmp_path / "coverage.json",
        branch_coverage=False,
    )

    with pytest.raises(SystemExit, match="branch coverage enabled"):
        gate.run(coverage_json=report_path, fail_under=90.0)


def test_branch_coverage_gate_rejects_inconsistent_counters(tmp_path: Path) -> None:
    gate = load_branch_coverage_gate()
    report_path = write_coverage_report(
        tmp_path / "coverage.json",
        covered_branches=101,
        num_branches=100,
    )

    with pytest.raises(SystemExit, match="inconsistent"):
        gate.run(coverage_json=report_path, fail_under=90.0)
