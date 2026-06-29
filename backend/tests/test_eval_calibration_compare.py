import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path
from types import ModuleType
from typing import Any


def load_compare_cli() -> ModuleType:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "compare_eval_calibration.py"
    spec = importlib.util.spec_from_file_location("compare_eval_calibration", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load calibration compare CLI from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def manifest_payload(
    *,
    passed: bool = True,
    records: int = 10,
    cases: int = 5,
    retrieval_recall: float = 1.0,
    cer: float = 0.05,
) -> dict[str, Any]:
    return {
        "started_at": "2026-06-28T09:05:17+00:00",
        "completed_at": "2026-06-28T09:05:18+00:00",
        "passed": passed,
        "target_count": 1,
        "max_records": records,
        "max_cases": cases,
        "metric_gates": [],
        "targets": [
            {
                "key": "squad",
                "suite": "squad-v2",
                "description": "SQuAD calibration.",
                "passed": passed,
                "report_passed": passed,
                "gates_passed": passed,
                "case_count": cases,
                "metrics": {
                    "retrieval_recall": retrieval_recall,
                    "cer": cer,
                    "ignored_text_metric": "n/a",
                },
                "gates": [],
                "dataset": {
                    "profile": "squad-dev-v2",
                    "suite": "squad",
                    "path": "../evals/datasets/squad-dev-v2-sample.json",
                    "records": records,
                    "reused": False,
                    "source": "https://rajpurkar.github.io/SQuAD-explorer/",
                    "source_url": "https://rajpurkar.github.io/SQuAD-explorer/dataset/dev-v2.0.json",
                    "license_note": "SQuAD data is distributed by the Stanford SQuAD project.",
                },
                "reports": {
                    "json": "../evals/reports/calibration/real-squad-dev-v2.json",
                    "markdown": "../evals/reports/calibration/real-squad-dev-v2.md",
                },
            }
        ],
    }


def test_compare_manifests_passes_for_larger_stable_candidate() -> None:
    cli = load_compare_cli()
    baseline = manifest_payload(records=10, cases=5, retrieval_recall=0.95, cer=0.05)
    candidate = manifest_payload(records=25, cases=10, retrieval_recall=0.94, cer=0.06)

    comparison = cli.compare_manifests(
        baseline=baseline,
        candidate=candidate,
        max_regression=0.02,
        title="Trend",
    )
    markdown = cli.render_markdown(comparison)

    assert comparison["passed"] is True
    assert comparison["targets"][0]["records"]["delta"] == 15
    assert comparison["targets"][0]["cases"]["delta"] == 5
    assert comparison["targets"][0]["metrics"][0]["name"] == "cer"
    assert comparison["targets"][0]["metrics"][0]["direction"] == "lower_is_better"
    assert "../evals/datasets" not in markdown
    assert "../evals/reports" not in markdown
    assert "Allowed regression tolerance: 0.02" in markdown


def test_compare_manifests_fails_metric_regression() -> None:
    cli = load_compare_cli()
    baseline = manifest_payload(records=10, cases=5, retrieval_recall=0.95)
    candidate = manifest_payload(records=25, cases=10, retrieval_recall=0.90)

    comparison = cli.compare_manifests(
        baseline=baseline,
        candidate=candidate,
        max_regression=0.01,
        title="Trend",
    )

    assert comparison["passed"] is False
    metric = next(
        metric
        for metric in comparison["targets"][0]["metrics"]
        if metric["name"] == "retrieval_recall"
    )
    assert metric["passed"] is False
    assert metric["delta"] == -0.04999999999999993


def test_compare_manifests_rejects_missing_candidate_target() -> None:
    cli = load_compare_cli()
    baseline = manifest_payload()
    candidate = manifest_payload()
    candidate["targets"] = []

    try:
        cli.compare_manifests(
            baseline=baseline,
            candidate=candidate,
            max_regression=0.0,
            title="Trend",
        )
    except cli.CalibrationComparisonError as exc:
        assert "at least one target" in str(exc)
    else:
        raise AssertionError("Expected empty candidate manifest to fail")


def test_compare_manifests_rejects_missing_candidate_metric() -> None:
    cli = load_compare_cli()
    baseline = manifest_payload()
    candidate = deepcopy(baseline)
    del candidate["targets"][0]["metrics"]["retrieval_recall"]

    try:
        cli.compare_manifests(
            baseline=baseline,
            candidate=candidate,
            max_regression=0.0,
            title="Trend",
        )
    except cli.CalibrationComparisonError as exc:
        assert "missing baseline metric" in str(exc)
    else:
        raise AssertionError("Expected missing metric to fail")


def test_compare_manifests_rejects_dataset_profile_drift() -> None:
    cli = load_compare_cli()
    baseline = manifest_payload()
    candidate = deepcopy(baseline)
    candidate["targets"][0]["dataset"]["profile"] = "different-squad-profile"

    try:
        cli.compare_manifests(
            baseline=baseline,
            candidate=candidate,
            max_regression=0.0,
            title="Trend",
        )
    except cli.CalibrationComparisonError as exc:
        assert "changed dataset profile" in str(exc)
    else:
        raise AssertionError("Expected dataset profile drift to fail")


def test_compare_manifests_rejects_dataset_suite_drift() -> None:
    cli = load_compare_cli()
    baseline = manifest_payload()
    candidate = deepcopy(baseline)
    candidate["targets"][0]["dataset"]["suite"] = "natural-questions"

    try:
        cli.compare_manifests(
            baseline=baseline,
            candidate=candidate,
            max_regression=0.0,
            title="Trend",
        )
    except cli.CalibrationComparisonError as exc:
        assert "changed dataset suite" in str(exc)
    else:
        raise AssertionError("Expected dataset suite drift to fail")


def test_cli_writes_comparison_markdown(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    cli = load_compare_cli()
    baseline_path = tmp_path / "baseline.json"
    candidate_path = tmp_path / "candidate.json"
    output_path = tmp_path / "trend.md"
    baseline_path.write_text(json.dumps(manifest_payload()), encoding="utf-8")
    candidate_path.write_text(json.dumps(manifest_payload(records=12, cases=6)), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "compare_eval_calibration.py",
            "--baseline",
            str(baseline_path),
            "--candidate",
            str(candidate_path),
            "--output",
            str(output_path),
            "--title",
            "CLI Trend",
        ],
    )

    assert cli.main() == 0
    assert output_path.read_text(encoding="utf-8").startswith("# CLI Trend")
