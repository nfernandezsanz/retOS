import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def load_gate_cli() -> ModuleType:
    script_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "check_eval_calibration_evidence.py"
    )
    spec = importlib.util.spec_from_file_location("check_eval_calibration_evidence", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load calibration evidence gate from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def evidence_markdown(
    *,
    status: str = "PASS",
    records: int = 200,
    cases: int = 40,
    gate_status: str = "PASS",
    include_local_path: bool = False,
    dataset: str = "squad-dev-v2",
) -> str:
    local_path_note = "\n- Raw path: ../evals/datasets/sample.json\n" if include_local_path else ""
    target_row = (
        f"| squad | squad-v2 | {status} | {cases} | {dataset} | {records} | "
        "https://example.test/squad.json |"
    )
    return f"""# Calibration Evidence

Status: {status}

## Reproduction

```bash
make eval-calibration MAX_RECORDS=200 MAX_CASES=40 METRIC_GATES='squad.retrieval_recall=0.8'
```

## Targets

| Target | Suite | Status | Cases | Dataset | Records | Source URL |
| --- | --- | --- | ---: | --- | ---: | --- |
{target_row}

## squad Metrics

SQuAD calibration.

| Gate | Minimum | Actual | Status |
| --- | ---: | ---: | --- |
| retrieval_recall | 0.8 | 1 | {gate_status} |

## Notes
{local_path_note}
- Source URLs and license notes come from the calibration manifest.
"""


def write_evidence(tmp_path: Path, markdown: str) -> Path:
    path = tmp_path / "calibration.md"
    path.write_text(markdown, encoding="utf-8")
    return path


def test_calibration_evidence_gate_accepts_path_safe_passing_evidence(
    tmp_path: Path,
) -> None:
    cli = load_gate_cli()
    evidence_path = write_evidence(tmp_path, evidence_markdown())

    cli.validate_evidence(
        evidence_path=evidence_path,
        required_targets=("squad",),
        required_gates=("squad.retrieval_recall",),
        min_records=200,
        min_cases=40,
    )


def test_calibration_evidence_gate_rejects_small_samples(tmp_path: Path) -> None:
    cli = load_gate_cli()
    evidence_path = write_evidence(tmp_path, evidence_markdown(records=199, cases=40))

    try:
        cli.validate_evidence(
            evidence_path=evidence_path,
            required_targets=("squad",),
            required_gates=("squad.retrieval_recall",),
            min_records=200,
            min_cases=40,
        )
    except cli.EvalCalibrationEvidenceError as exc:
        assert "records 199 below required 200" in str(exc)
    else:
        raise AssertionError("Expected small calibration sample to fail")


def test_calibration_evidence_gate_rejects_missing_gate(tmp_path: Path) -> None:
    cli = load_gate_cli()
    evidence_path = write_evidence(tmp_path, evidence_markdown())

    try:
        cli.validate_evidence(
            evidence_path=evidence_path,
            required_targets=("squad",),
            required_gates=("squad.grounded_answer",),
            min_records=200,
            min_cases=40,
        )
    except cli.EvalCalibrationEvidenceError as exc:
        assert "missing gate: squad.grounded_answer" in str(exc)
    else:
        raise AssertionError("Expected missing calibration gate to fail")


def test_calibration_evidence_gate_rejects_local_paths(tmp_path: Path) -> None:
    cli = load_gate_cli()
    evidence_path = write_evidence(tmp_path, evidence_markdown(include_local_path=True))

    try:
        cli.validate_evidence(
            evidence_path=evidence_path,
            required_targets=("squad",),
            required_gates=("squad.retrieval_recall",),
            min_records=200,
            min_cases=40,
        )
    except cli.EvalCalibrationEvidenceError as exc:
        assert "evidence must omit local path pattern" in str(exc)
    else:
        raise AssertionError("Expected local path leakage to fail")


def test_calibration_evidence_gate_rejects_missing_dataset_profile(
    tmp_path: Path,
) -> None:
    cli = load_gate_cli()
    evidence_path = write_evidence(tmp_path, evidence_markdown(dataset="-"))

    try:
        cli.validate_evidence(
            evidence_path=evidence_path,
            required_targets=("squad",),
            required_gates=("squad.retrieval_recall",),
            min_records=200,
            min_cases=40,
        )
    except cli.EvalCalibrationEvidenceError as exc:
        assert "dataset profile is missing" in str(exc)
    else:
        raise AssertionError("Expected missing dataset profile to fail")
