import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def load_gate_cli() -> ModuleType:
    script_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "check_eval_calibration_trend.py"
    )
    spec = importlib.util.spec_from_file_location("check_eval_calibration_trend", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load calibration trend gate from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def trend_markdown(
    *,
    status: str = "PASS",
    candidate_records: int = 200,
    candidate_cases: int = 40,
    records_delta: int = 100,
    cases_delta: int = 10,
    metric_delta: float = 0.0,
    metric_status: str = "PASS",
    include_local_path: bool = False,
) -> str:
    local_path_note = (
        "\n- Raw path: evals/reports/calibration/manifest.json\n" if include_local_path else ""
    )
    target_row = (
        f"| squad | squad-v2 | {status} | {records_delta} | {cases_delta} | "
        "squad-dev-v2 | https://example.test/squad.json |"
    )
    metric_row = (
        f"| retrieval_recall | 1 | {1 + metric_delta:g} | {metric_delta:g} | "
        f"higher_is_better | {metric_status} |"
    )
    return f"""# Calibration Trend Evidence

Status: {status}

| Field | Baseline | Candidate |
| --- | ---: | ---: |
| Passed | True | True |
| Targets | 1 | 1 |
| Max records | 100 | {candidate_records} |
| Max cases | 30 | {candidate_cases} |

Allowed regression tolerance: 0

## Targets

| Target | Suite | Status | Records Delta | Cases Delta | Dataset | Source URL |
| --- | --- | --- | ---: | ---: | --- | --- |
{target_row}

## squad Metrics

| Metric | Baseline | Candidate | Delta | Direction | Status |
| --- | ---: | ---: | ---: | --- | --- |
{metric_row}

## Notes
{local_path_note}
- Source URLs and license notes come from the calibration manifests.
"""


def write_evidence(tmp_path: Path, markdown: str) -> Path:
    path = tmp_path / "calibration-trend.md"
    path.write_text(markdown, encoding="utf-8")
    return path


def validate_default(cli: ModuleType, evidence_path: Path) -> None:
    cli.validate_trend(
        evidence_path=evidence_path,
        required_targets=("squad",),
        min_baseline_records=100,
        min_candidate_records=200,
        min_baseline_cases=30,
        min_candidate_cases=40,
        min_record_delta=100,
        min_case_delta=10,
        max_regression=0.0,
    )


def test_calibration_trend_gate_accepts_path_safe_passing_trend(tmp_path: Path) -> None:
    cli = load_gate_cli()
    evidence_path = write_evidence(tmp_path, trend_markdown())

    validate_default(cli, evidence_path)


def test_calibration_trend_gate_rejects_small_candidate_sample(tmp_path: Path) -> None:
    cli = load_gate_cli()
    evidence_path = write_evidence(tmp_path, trend_markdown(candidate_records=199))

    try:
        validate_default(cli, evidence_path)
    except cli.EvalCalibrationTrendError as exc:
        assert "candidate max records 199 below required 200" in str(exc)
    else:
        raise AssertionError("Expected small candidate sample to fail")


def test_calibration_trend_gate_rejects_metric_regression(tmp_path: Path) -> None:
    cli = load_gate_cli()
    evidence_path = write_evidence(
        tmp_path, trend_markdown(metric_delta=-0.01, metric_status="PASS")
    )

    try:
        validate_default(cli, evidence_path)
    except cli.EvalCalibrationTrendError as exc:
        assert "squad.retrieval_recall regressed by -0.01" in str(exc)
    else:
        raise AssertionError("Expected metric regression to fail")


def test_calibration_trend_gate_rejects_local_paths(tmp_path: Path) -> None:
    cli = load_gate_cli()
    evidence_path = write_evidence(tmp_path, trend_markdown(include_local_path=True))

    try:
        validate_default(cli, evidence_path)
    except cli.EvalCalibrationTrendError as exc:
        assert "trend evidence must omit local path pattern" in str(exc)
    else:
        raise AssertionError("Expected local path leakage to fail")
