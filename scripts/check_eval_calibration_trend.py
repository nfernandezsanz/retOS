#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_EVIDENCE = Path(
    "docs/releases/evidence/2026.06.28-alpha.1-calibration-trend.md"
)
DEFAULT_TARGETS = ("squad", "hotpotqa", "hotpotqa-agent", "natural-questions")
LOCAL_PATH_PATTERNS = ("../evals/", "evals/datasets/", "evals/reports/")
LOWER_IS_BETTER_METRIC_HINTS = ("_error_rate", "cer", "wer")


class EvalCalibrationTrendError(RuntimeError):
    pass


@dataclass(frozen=True)
class TargetTrend:
    key: str
    suite: str
    status: str
    records_delta: int
    cases_delta: int
    dataset: str
    source_url: str


@dataclass(frozen=True)
class MetricTrend:
    target: str
    metric: str
    baseline: float
    candidate: float
    delta: float
    direction: str
    status: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate path-safe RetOS calibration trend evidence for local "
            "release-promotion review. This does not fetch datasets or contact GitHub."
        )
    )
    parser.add_argument(
        "--evidence",
        type=Path,
        default=DEFAULT_EVIDENCE,
        help="Markdown calibration trend evidence file to validate.",
    )
    parser.add_argument(
        "--min-baseline-records",
        type=int,
        default=100,
        help="Minimum baseline record cap expected in the trend summary.",
    )
    parser.add_argument(
        "--min-candidate-records",
        type=int,
        default=200,
        help="Minimum candidate record cap expected in the trend summary.",
    )
    parser.add_argument(
        "--min-baseline-cases",
        type=int,
        default=30,
        help="Minimum baseline case cap expected in the trend summary.",
    )
    parser.add_argument(
        "--min-candidate-cases",
        type=int,
        default=40,
        help="Minimum candidate case cap expected in the trend summary.",
    )
    parser.add_argument(
        "--min-record-delta",
        type=int,
        default=100,
        help="Minimum per-target record growth expected in the trend table.",
    )
    parser.add_argument(
        "--min-case-delta",
        type=int,
        default=10,
        help="Minimum per-target case growth expected in the trend table.",
    )
    parser.add_argument(
        "--max-regression",
        type=float,
        default=0.0,
        help="Maximum tolerated regression for each metric delta.",
    )
    parser.add_argument(
        "--target",
        action="append",
        help="Required target key. May be repeated. Defaults to the alpha release targets.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        validate_trend(
            evidence_path=args.evidence,
            required_targets=tuple(args.target or DEFAULT_TARGETS),
            min_baseline_records=args.min_baseline_records,
            min_candidate_records=args.min_candidate_records,
            min_baseline_cases=args.min_baseline_cases,
            min_candidate_cases=args.min_candidate_cases,
            min_record_delta=args.min_record_delta,
            min_case_delta=args.min_case_delta,
            max_regression=args.max_regression,
        )
    except EvalCalibrationTrendError as exc:
        print(f"Eval calibration trend failed: {exc}", file=sys.stderr)
        return 1
    print(
        "Eval calibration trend OK: trend evidence is path-safe, complete, "
        "and regression-gated."
    )
    return 0


def validate_trend(
    *,
    evidence_path: Path,
    required_targets: tuple[str, ...],
    min_baseline_records: int,
    min_candidate_records: int,
    min_baseline_cases: int,
    min_candidate_cases: int,
    min_record_delta: int,
    min_case_delta: int,
    max_regression: float,
) -> None:
    for name, value in (
        ("--min-baseline-records", min_baseline_records),
        ("--min-candidate-records", min_candidate_records),
        ("--min-baseline-cases", min_baseline_cases),
        ("--min-candidate-cases", min_candidate_cases),
    ):
        require(value > 0, f"{name} must be greater than zero")
    require(max_regression >= 0, "--max-regression must be zero or greater")
    if not evidence_path.is_file():
        raise EvalCalibrationTrendError(f"evidence file not found: {evidence_path}")

    content = evidence_path.read_text(encoding="utf-8")
    require("Status: PASS" in content, "trend evidence status must be PASS")
    require(
        f"Allowed regression tolerance: {max_regression:g}" in content,
        "allowed regression tolerance must match the gate",
    )
    for pattern in LOCAL_PATH_PATTERNS:
        require(
            pattern not in content,
            f"trend evidence must omit local path pattern: {pattern}",
        )

    fields = parse_summary_fields(content)
    require(
        fields.get("Passed") == ("True", "True"),
        "baseline and candidate must both be marked passed",
    )
    require_int_field(fields, "Max records", 0, min_baseline_records)
    require_int_field(fields, "Max records", 1, min_candidate_records)
    require_int_field(fields, "Max cases", 0, min_baseline_cases)
    require_int_field(fields, "Max cases", 1, min_candidate_cases)

    targets = parse_targets(content)
    missing_targets = sorted(set(required_targets) - set(targets))
    require(not missing_targets, "missing target(s): " + ", ".join(missing_targets))
    for target_key in required_targets:
        target = targets[target_key]
        require(target.status == "PASS", f"{target_key} status must be PASS")
        require(
            target.records_delta >= min_record_delta,
            (
                f"{target_key} records delta {target.records_delta} below required "
                f"{min_record_delta}"
            ),
        )
        require(
            target.cases_delta >= min_case_delta,
            f"{target_key} cases delta {target.cases_delta} below required {min_case_delta}",
        )
        require(
            target.source_url.startswith("https://"),
            f"{target_key} source URL must be https",
        )

    metrics = parse_metrics(content)
    for target_key in required_targets:
        target_metrics = metrics.get(target_key, [])
        require(target_metrics, f"{target_key} must include metric trend rows")
        for metric in target_metrics:
            require(
                metric.status == "PASS", f"{target_key}.{metric.metric} must be PASS"
            )
            require_metric_delta(metric, max_regression)


def parse_summary_fields(content: str) -> dict[str, tuple[str, str]]:
    fields: dict[str, tuple[str, str]] = {}
    for line in content.splitlines():
        cells = table_cells(line)
        if len(cells) != 3:
            continue
        if cells[0] in {"Field", "---"}:
            continue
        fields[cells[0]] = (cells[1], cells[2])
    if not fields:
        raise EvalCalibrationTrendError("no trend summary table found")
    return fields


def parse_targets(content: str) -> dict[str, TargetTrend]:
    targets: dict[str, TargetTrend] = {}
    for line in content.splitlines():
        cells = table_cells(line)
        if len(cells) != 7:
            continue
        if cells[0] in {"Target", "---"}:
            continue
        if cells[2] not in {"PASS", "FAIL"}:
            continue
        try:
            records_delta = int(cells[3])
            cases_delta = int(cells[4])
        except ValueError:
            continue
        targets[cells[0]] = TargetTrend(
            key=cells[0],
            suite=cells[1],
            status=cells[2],
            records_delta=records_delta,
            cases_delta=cases_delta,
            dataset=cells[5],
            source_url=cells[6],
        )
    if not targets:
        raise EvalCalibrationTrendError("no target trend table rows found")
    return targets


def parse_metrics(content: str) -> dict[str, list[MetricTrend]]:
    metrics: dict[str, list[MetricTrend]] = {}
    current_target: str | None = None
    for line in content.splitlines():
        metric_heading = re.fullmatch(r"## ([a-z0-9-]+) Metrics", line.strip())
        if metric_heading is not None:
            current_target = metric_heading.group(1)
            metrics.setdefault(current_target, [])
            continue
        if current_target is None:
            continue
        cells = table_cells(line)
        if len(cells) != 6:
            continue
        if cells[0] in {"Metric", "---"} or cells[5] not in {"PASS", "FAIL"}:
            continue
        try:
            baseline = float(cells[1])
            candidate = float(cells[2])
            delta = float(cells[3])
        except ValueError:
            continue
        metrics[current_target].append(
            MetricTrend(
                target=current_target,
                metric=cells[0],
                baseline=baseline,
                candidate=candidate,
                delta=delta,
                direction=cells[4],
                status=cells[5],
            )
        )
    return metrics


def require_metric_delta(metric: MetricTrend, max_regression: float) -> None:
    lower_is_better = metric.direction == "lower_is_better" or any(
        hint in metric.metric for hint in LOWER_IS_BETTER_METRIC_HINTS
    )
    higher_is_better = metric.direction == "higher_is_better" and not lower_is_better
    if lower_is_better:
        require(
            metric.delta <= max_regression,
            (
                f"{metric.target}.{metric.metric} regressed by {metric.delta:g}; "
                f"maximum allowed is {max_regression:g}"
            ),
        )
        return
    require(
        higher_is_better,
        f"{metric.target}.{metric.metric} has unknown direction: {metric.direction}",
    )
    require(
        metric.delta >= -max_regression,
        (
            f"{metric.target}.{metric.metric} regressed by {metric.delta:g}; "
            f"maximum allowed is {max_regression:g}"
        ),
    )


def require_int_field(
    fields: dict[str, tuple[str, str]], name: str, index: int, minimum: int
) -> None:
    values = fields.get(name)
    require(values is not None, f"missing summary field: {name}")
    try:
        actual = int(values[index])
    except ValueError as exc:
        raise EvalCalibrationTrendError(f"{name} must be an integer") from exc
    label = "baseline" if index == 0 else "candidate"
    require(
        actual >= minimum, f"{label} {name.lower()} {actual} below required {minimum}"
    )


def table_cells(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return []
    return [cell.strip() for cell in stripped.strip("|").split("|")]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvalCalibrationTrendError(message)


if __name__ == "__main__":
    raise SystemExit(main())
