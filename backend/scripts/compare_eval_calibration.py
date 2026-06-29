from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


class CalibrationComparisonError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare two RetOS eval calibration manifests and produce path-safe trend "
            "evidence for release promotion reviews."
        )
    )
    parser.add_argument("--baseline", type=Path, required=True, help="Baseline manifest.json.")
    parser.add_argument("--candidate", type=Path, required=True, help="Candidate manifest.json.")
    parser.add_argument(
        "--max-regression",
        type=float,
        default=0.0,
        help=(
            "Allowed metric regression tolerance. Higher-is-better metrics may drop by "
            "this amount; lower-is-better metrics may rise by this amount."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Markdown trend evidence file to write. Omit to print to stdout.",
    )
    parser.add_argument(
        "--title",
        default="Real-Dataset Calibration Trend Evidence",
        help="Markdown title for the trend evidence document.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        comparison = compare_manifests(
            baseline=load_manifest(args.baseline),
            candidate=load_manifest(args.candidate),
            max_regression=args.max_regression,
            title=args.title,
        )
    except CalibrationComparisonError as exc:
        print(f"Calibration comparison error: {exc}", file=sys.stderr)
        return 2

    markdown = render_markdown(comparison)
    if args.output is None:
        print(markdown, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(markdown, encoding="utf-8")
    return 0 if comparison["passed"] else 1


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise CalibrationComparisonError(f"Manifest not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CalibrationComparisonError(f"Manifest is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise CalibrationComparisonError("Manifest root must be an object")
    return payload


def compare_manifests(
    *,
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    max_regression: float,
    title: str,
) -> dict[str, Any]:
    if max_regression < 0:
        raise CalibrationComparisonError("--max-regression cannot be negative")
    if candidate.get("passed") is not True:
        candidate_status = "candidate manifest did not pass its own gates"
    else:
        candidate_status = ""

    baseline_targets = targets_by_key(baseline)
    candidate_targets = targets_by_key(candidate)
    missing_targets = sorted(set(baseline_targets) - set(candidate_targets))
    if missing_targets:
        raise CalibrationComparisonError(
            "Candidate manifest is missing baseline target(s): " + ", ".join(missing_targets)
        )

    target_comparisons = [
        compare_target(
            key=key,
            baseline=baseline_targets[key],
            candidate=candidate_targets[key],
            max_regression=max_regression,
        )
        for key in sorted(baseline_targets)
    ]
    passed = (
        candidate_status == ""
        and all(target["passed"] for target in target_comparisons)
        and bool(target_comparisons)
    )
    return {
        "title": title,
        "passed": passed,
        "status": "PASS" if passed else "FAIL",
        "candidate_status": candidate_status,
        "max_regression": max_regression,
        "baseline": manifest_summary(baseline),
        "candidate": manifest_summary(candidate),
        "targets": target_comparisons,
    }


def targets_by_key(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    targets = manifest.get("targets")
    if not isinstance(targets, list) or not targets:
        raise CalibrationComparisonError("Manifest must contain at least one target")
    keyed: dict[str, dict[str, Any]] = {}
    for target in targets:
        if not isinstance(target, dict):
            raise CalibrationComparisonError("Every manifest target must be an object")
        key = target.get("key")
        if not isinstance(key, str) or not key:
            raise CalibrationComparisonError("Every manifest target must include a key")
        if key in keyed:
            raise CalibrationComparisonError(f"Duplicate target key in manifest: {key}")
        keyed[key] = target
    return keyed


def compare_target(
    *,
    key: str,
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    max_regression: float,
) -> dict[str, Any]:
    candidate_dataset = dataset_metadata(key, baseline=baseline, candidate=candidate)
    baseline_records = dataset_records(baseline)
    candidate_records = dataset_records(candidate)
    baseline_cases = int_value(baseline.get("case_count"))
    candidate_cases = int_value(candidate.get("case_count"))
    metrics = compare_metrics(
        baseline_metrics=metrics_payload(baseline),
        candidate_metrics=metrics_payload(candidate),
        max_regression=max_regression,
    )
    records_passed = candidate_records >= baseline_records
    cases_passed = candidate_cases >= baseline_cases
    metrics_passed = all(metric["passed"] for metric in metrics)
    candidate_passed = candidate.get("passed") is True
    return {
        "key": key,
        "suite": string_value(candidate.get("suite")),
        "passed": records_passed and cases_passed and metrics_passed and candidate_passed,
        "candidate_passed": candidate_passed,
        "records": {
            "baseline": baseline_records,
            "candidate": candidate_records,
            "delta": candidate_records - baseline_records,
            "passed": records_passed,
        },
        "cases": {
            "baseline": baseline_cases,
            "candidate": candidate_cases,
            "delta": candidate_cases - baseline_cases,
            "passed": cases_passed,
        },
        "metrics": metrics,
        "dataset": {
            "profile": candidate_dataset["profile"],
            "suite": candidate_dataset["suite"],
            "source_url": candidate_dataset["source_url"],
            "license_note": candidate_dataset["license_note"],
        },
    }


def compare_metrics(
    *,
    baseline_metrics: dict[str, float],
    candidate_metrics: dict[str, float],
    max_regression: float,
) -> list[dict[str, Any]]:
    missing = sorted(set(baseline_metrics) - set(candidate_metrics))
    if missing:
        raise CalibrationComparisonError(
            "Candidate metrics are missing baseline metric(s): " + ", ".join(missing)
        )
    comparisons: list[dict[str, Any]] = []
    for name in sorted(baseline_metrics):
        baseline_value = baseline_metrics[name]
        candidate_value = candidate_metrics[name]
        delta = candidate_value - baseline_value
        lower_is_better = is_lower_better_metric(name)
        if lower_is_better:
            passed = candidate_value <= baseline_value + max_regression
        else:
            passed = candidate_value >= baseline_value - max_regression
        comparisons.append(
            {
                "name": name,
                "baseline": baseline_value,
                "candidate": candidate_value,
                "delta": delta,
                "direction": "lower_is_better" if lower_is_better else "higher_is_better",
                "passed": passed,
            }
        )
    return comparisons


def is_lower_better_metric(name: str) -> bool:
    normalized = name.lower()
    return normalized.endswith("_error_rate") or normalized in {
        "cer",
        "wer",
        "error_rate",
    }


def manifest_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "passed": manifest.get("passed") is True,
        "started_at": string_value(manifest.get("started_at")),
        "completed_at": string_value(manifest.get("completed_at")),
        "max_records": int_value(manifest.get("max_records")),
        "max_cases": int_value(manifest.get("max_cases")),
        "target_count": int_value(manifest.get("target_count")),
    }


def dataset_metadata(
    key: str,
    *,
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, str]:
    baseline_dataset = dataset_payload(baseline)
    candidate_dataset = dataset_payload(candidate)
    for field in ("profile", "suite"):
        baseline_value = string_value(baseline_dataset.get(field))
        candidate_value = string_value(candidate_dataset.get(field))
        if not baseline_value:
            raise CalibrationComparisonError(f"Baseline target {key} is missing dataset {field}")
        if not candidate_value:
            raise CalibrationComparisonError(f"Candidate target {key} is missing dataset {field}")
        if candidate_value != baseline_value:
            raise CalibrationComparisonError(
                f"Candidate target {key} changed dataset {field} "
                f"from {baseline_value} to {candidate_value}"
            )
    return {
        "profile": string_value(candidate_dataset.get("profile")),
        "suite": string_value(candidate_dataset.get("suite")),
        "source_url": string_value(candidate_dataset.get("source_url")),
        "license_note": string_value(candidate_dataset.get("license_note")),
    }


def dataset_payload(target: dict[str, Any]) -> dict[str, Any]:
    dataset = target.get("dataset")
    if not isinstance(dataset, dict):
        raise CalibrationComparisonError(f"Target {target.get('key')} is missing dataset metadata")
    return dataset


def dataset_records(target: dict[str, Any]) -> int:
    return int_value(dataset_payload(target).get("records"))


def metrics_payload(target: dict[str, Any]) -> dict[str, float]:
    metrics = target.get("metrics")
    if not isinstance(metrics, dict):
        raise CalibrationComparisonError(f"Target {target.get('key')} is missing metrics")
    numeric_metrics = {
        name: float(value)
        for name, value in metrics.items()
        if isinstance(name, str) and isinstance(value, int | float) and not isinstance(value, bool)
    }
    if not numeric_metrics:
        raise CalibrationComparisonError(f"Target {target.get('key')} has no numeric metrics")
    return numeric_metrics


def render_markdown(comparison: dict[str, Any]) -> str:
    lines = [
        f"# {comparison['title']}",
        "",
        f"Status: {comparison['status']}",
        "",
        "| Field | Baseline | Candidate |",
        "| --- | ---: | ---: |",
        f"| Passed | {comparison['baseline']['passed']} | {comparison['candidate']['passed']} |",
        (
            f"| Targets | {comparison['baseline']['target_count']} | "
            f"{comparison['candidate']['target_count']} |"
        ),
        (
            f"| Max records | {comparison['baseline']['max_records']} | "
            f"{comparison['candidate']['max_records']} |"
        ),
        (
            f"| Max cases | {comparison['baseline']['max_cases']} | "
            f"{comparison['candidate']['max_cases']} |"
        ),
        "",
        f"Allowed regression tolerance: {format_number(comparison['max_regression'])}",
        "",
    ]
    if comparison["candidate_status"]:
        lines.extend([f"Candidate status: {comparison['candidate_status']}", ""])

    lines.extend(
        [
            "## Targets",
            "",
            "| Target | Suite | Status | Records Delta | Cases Delta | Dataset | Source URL |",
            "| --- | --- | --- | ---: | ---: | --- | --- |",
        ]
    )
    for target in comparison["targets"]:
        lines.append(
            (
                "| {key} | {suite} | {status} | {records_delta} | {cases_delta} | "
                "{profile} | {source_url} |"
            ).format(
                key=target["key"],
                suite=target["suite"],
                status="PASS" if target["passed"] else "FAIL",
                records_delta=target["records"]["delta"],
                cases_delta=target["cases"]["delta"],
                profile=target["dataset"]["profile"],
                source_url=markdown_value(target["dataset"]["source_url"]),
            )
        )
    lines.append("")

    for target in comparison["targets"]:
        lines.extend(
            [
                f"## {target['key']} Metrics",
                "",
                "| Metric | Baseline | Candidate | Delta | Direction | Status |",
                "| --- | ---: | ---: | ---: | --- | --- |",
            ]
        )
        for metric in target["metrics"]:
            lines.append(
                "| {name} | {baseline} | {candidate} | {delta} | {direction} | {status} |".format(
                    name=metric["name"],
                    baseline=format_number(metric["baseline"]),
                    candidate=format_number(metric["candidate"]),
                    delta=format_number(metric["delta"]),
                    direction=metric["direction"],
                    status="PASS" if metric["passed"] else "FAIL",
                )
            )
        lines.extend(
            [
                "",
                "| Provenance | Value |",
                "| --- | --- |",
                f"| Dataset profile | {target['dataset']['profile']} |",
                f"| Dataset suite | {target['dataset']['suite']} |",
                f"| Source URL | {markdown_value(target['dataset']['source_url'])} |",
                f"| License note | {markdown_value(target['dataset']['license_note'])} |",
                "",
            ]
        )

    lines.extend(
        [
            "## Notes",
            "",
            "- Local dataset paths and report paths are intentionally omitted.",
            "- Candidate slices must keep at least the baseline record and case counts.",
            "- Higher-is-better metrics may not regress beyond the configured tolerance.",
            "- `*_error_rate`, `cer`, and `wer` are treated as lower-is-better metrics.",
            "",
        ]
    )
    return "\n".join(lines)


def int_value(value: Any) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return 0


def string_value(value: Any) -> str:
    return value if isinstance(value, str) else ""


def markdown_value(value: object) -> str:
    if value is None or value == "":
        return "-"
    return str(value)


def format_number(value: float) -> str:
    return f"{value:.4g}"


if __name__ == "__main__":
    sys.exit(main())
