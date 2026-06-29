#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_EVIDENCE = Path("docs/releases/evidence/2026.06.28-alpha.1-calibration.md")
DEFAULT_TARGETS = ("squad", "hotpotqa", "hotpotqa-agent", "natural-questions")
DEFAULT_GATES = (
    "squad.retrieval_recall",
    "hotpotqa.retrieval_recall",
    "hotpotqa-agent.multi_hop_support",
    "natural-questions.retrieval_recall",
)
LOCAL_PATH_PATTERNS = ("../evals/", "evals/datasets/", "evals/reports/")


class EvalCalibrationEvidenceError(RuntimeError):
    pass


@dataclass(frozen=True)
class TargetEvidence:
    key: str
    suite: str
    status: str
    cases: int
    dataset: str
    records: int
    source_url: str


@dataclass(frozen=True)
class GateEvidence:
    target: str
    metric: str
    minimum: float
    actual: float
    status: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate path-safe RetOS real-dataset calibration evidence for local "
            "release-promotion review. This does not fetch datasets or contact GitHub."
        )
    )
    parser.add_argument(
        "--evidence",
        type=Path,
        default=DEFAULT_EVIDENCE,
        help="Markdown calibration evidence file to validate.",
    )
    parser.add_argument(
        "--min-records",
        type=int,
        default=200,
        help="Minimum sampled records required for each target.",
    )
    parser.add_argument(
        "--min-cases",
        type=int,
        default=40,
        help="Minimum evaluated cases required for each target.",
    )
    parser.add_argument(
        "--target",
        action="append",
        help="Required target key. May be repeated. Defaults to the alpha release targets.",
    )
    parser.add_argument(
        "--required-gate",
        action="append",
        metavar="TARGET.METRIC",
        help="Required PASS gate. May be repeated. Defaults to the alpha release gates.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        validate_evidence(
            evidence_path=args.evidence,
            required_targets=tuple(args.target or DEFAULT_TARGETS),
            required_gates=tuple(args.required_gate or DEFAULT_GATES),
            min_records=args.min_records,
            min_cases=args.min_cases,
        )
    except EvalCalibrationEvidenceError as exc:
        print(f"Eval calibration evidence failed: {exc}", file=sys.stderr)
        return 1
    print(
        "Eval calibration evidence OK: release calibration evidence is path-safe, "
        "complete, and gate-backed."
    )
    return 0


def validate_evidence(
    *,
    evidence_path: Path,
    required_targets: tuple[str, ...],
    required_gates: tuple[str, ...],
    min_records: int,
    min_cases: int,
) -> None:
    if min_records < 1:
        raise EvalCalibrationEvidenceError("--min-records must be greater than zero")
    if min_cases < 1:
        raise EvalCalibrationEvidenceError("--min-cases must be greater than zero")
    if not evidence_path.is_file():
        raise EvalCalibrationEvidenceError(f"evidence file not found: {evidence_path}")
    content = evidence_path.read_text(encoding="utf-8")
    require("Status: PASS" in content, "evidence status must be PASS")
    require("make eval-calibration" in content, "reproduction command is missing")
    require(
        "METRIC_GATES=" in content, "reproduction command must include metric gates"
    )
    for pattern in LOCAL_PATH_PATTERNS:
        require(
            pattern not in content, f"evidence must omit local path pattern: {pattern}"
        )

    targets = parse_targets(content)
    missing_targets = sorted(set(required_targets) - set(targets))
    require(not missing_targets, "missing target(s): " + ", ".join(missing_targets))
    for target_key in required_targets:
        target = targets[target_key]
        require(target.status == "PASS", f"{target_key} status must be PASS")
        require(
            target.records >= min_records,
            f"{target_key} records {target.records} below required {min_records}",
        )
        require(
            target.cases >= min_cases,
            f"{target_key} cases {target.cases} below required {min_cases}",
        )
        require(
            target.source_url.startswith("https://"),
            f"{target_key} source URL must be https",
        )
        require(
            bool(target.dataset.strip()) and target.dataset != "-",
            f"{target_key} dataset profile is missing",
        )

    gates = parse_gates(content)
    for raw_gate in required_gates:
        target_key, metric = parse_required_gate(raw_gate)
        gate = gates.get((target_key, metric))
        require(gate is not None, f"missing gate: {raw_gate}")
        require(gate.status == "PASS", f"{raw_gate} gate must be PASS")
        require(
            gate.actual >= gate.minimum,
            f"{raw_gate} actual {gate.actual:g} below minimum {gate.minimum:g}",
        )


def parse_targets(content: str) -> dict[str, TargetEvidence]:
    targets: dict[str, TargetEvidence] = {}
    for line in content.splitlines():
        cells = table_cells(line)
        if len(cells) != 7:
            continue
        if cells[0] in {"Target", "---"}:
            continue
        if cells[2] not in {"PASS", "FAIL"}:
            continue
        try:
            cases = int(cells[3])
            records = int(cells[5])
        except ValueError:
            continue
        targets[cells[0]] = TargetEvidence(
            key=cells[0],
            suite=cells[1],
            status=cells[2],
            cases=cases,
            dataset=cells[4],
            records=records,
            source_url=cells[6],
        )
    if not targets:
        raise EvalCalibrationEvidenceError("no target evidence table rows found")
    return targets


def parse_gates(content: str) -> dict[tuple[str, str], GateEvidence]:
    gates: dict[tuple[str, str], GateEvidence] = {}
    current_target: str | None = None
    for line in content.splitlines():
        metric_heading = re.fullmatch(r"## ([a-z0-9-]+) Metrics", line.strip())
        if metric_heading is not None:
            current_target = metric_heading.group(1)
            continue
        if current_target is None:
            continue
        cells = table_cells(line)
        if len(cells) != 4:
            continue
        if cells[0] in {"Gate", "---"} or cells[3] not in {"PASS", "FAIL"}:
            continue
        try:
            minimum = float(cells[1])
            actual = float(cells[2])
        except ValueError:
            continue
        gates[(current_target, cells[0])] = GateEvidence(
            target=current_target,
            metric=cells[0],
            minimum=minimum,
            actual=actual,
            status=cells[3],
        )
    return gates


def table_cells(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return []
    return [cell.strip() for cell in stripped.strip("|").split("|")]


def parse_required_gate(raw_gate: str) -> tuple[str, str]:
    target, separator, metric = raw_gate.partition(".")
    if not separator or not target or not metric:
        raise EvalCalibrationEvidenceError(
            f"required gate must use TARGET.METRIC format: {raw_gate}"
        )
    return target, metric


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvalCalibrationEvidenceError(message)


if __name__ == "__main__":
    raise SystemExit(main())
