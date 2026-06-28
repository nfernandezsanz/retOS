from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_coverage_report(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"Coverage report not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Coverage report is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"Coverage report must be a JSON object: {path}")
    return payload


def _branch_percentage(report: dict[str, Any]) -> tuple[float, int, int]:
    meta = report.get("meta")
    if not isinstance(meta, dict) or meta.get("branch_coverage") is not True:
        raise SystemExit("Coverage report was not generated with branch coverage enabled.")

    totals = report.get("totals")
    if not isinstance(totals, dict):
        raise SystemExit("Coverage report is missing totals.")

    branch_count = totals.get("num_branches")
    covered_count = totals.get("covered_branches")
    if not isinstance(branch_count, int) or not isinstance(covered_count, int):
        raise SystemExit("Coverage report totals are missing branch counters.")
    if branch_count < 0 or covered_count < 0 or covered_count > branch_count:
        raise SystemExit("Coverage report branch counters are inconsistent.")
    if branch_count == 0:
        return 100.0, covered_count, branch_count
    return (covered_count / branch_count) * 100, covered_count, branch_count


def run(*, coverage_json: Path, fail_under: float) -> int:
    report = _load_coverage_report(coverage_json)
    branch_percent, covered_count, branch_count = _branch_percentage(report)
    print(
        "Backend branch coverage: "
        f"{branch_percent:.2f}% ({covered_count}/{branch_count} branches)"
    )
    if branch_percent + 1e-9 < fail_under:
        print(
            "Backend branch coverage is below the required threshold: "
            f"{branch_percent:.2f}% < {fail_under:.2f}%"
        )
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate backend branch coverage.")
    parser.add_argument(
        "--coverage-json",
        type=Path,
        default=Path("coverage.json"),
        help="Path to a coverage.py JSON report generated with branch coverage enabled.",
    )
    parser.add_argument(
        "--fail-under",
        type=float,
        default=90.0,
        help="Minimum branch coverage percentage required.",
    )
    args = parser.parse_args()
    return run(coverage_json=args.coverage_json, fail_under=args.fail_under)


if __name__ == "__main__":
    raise SystemExit(main())
