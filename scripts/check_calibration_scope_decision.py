#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = ROOT / "docs/releases/evidence/calibration-scope-decision-template.md"

REQUIRED_HEADINGS = (
    "# Calibration Scope Decision Evidence Template",
    "## Candidate",
    "## Versioned Evidence",
    "## Pilot Scope Acceptance",
    "## Broader Trend Evidence",
    "## Risk Decision",
)

REQUIRED_FIELDS = (
    "Release version",
    "Immutable release tag",
    "Commit SHA",
    "Target environment",
    "Reviewer",
    "Review date",
    "Calibration evidence file",
    "Calibration trend evidence file",
    "`make eval-calibration-gate` output",
    "`make eval-calibration-trend-gate` output",
    "Baseline record cap",
    "Candidate record cap",
    "Baseline case cap",
    "Candidate case cap",
    "Required targets reviewed",
    "Metric gates reviewed",
    "Pilot scope accepted",
    "Accepted scope limit",
    "Pilot user group",
    "Pilot corpus boundary",
    "Pilot duration",
    "Manual review cadence",
    "Stop criteria",
    "Expansion trigger",
    "Promotion owner",
    "Follow-up issue",
    "Broader trend evidence attached",
    "Larger baseline record cap",
    "Larger candidate record cap",
    "Larger baseline case cap",
    "Larger candidate case cap",
    "Additional dataset targets",
    "Regression tolerance",
    "Trend decision",
    "Evidence artifact links",
    "Calibration decision",
    "Accepted risks",
    "Required follow-up issues",
    "Promotion impact",
)


class CalibrationScopeDecisionError(RuntimeError):
    pass


@dataclass(frozen=True)
class CalibrationScopeDecisionResult:
    headings: int
    fields: int


def _missing(required: tuple[str, ...], content: str) -> list[str]:
    return [item for item in required if item not in content]


def validate_calibration_scope_decision(
    template_path: Path = DEFAULT_TEMPLATE,
) -> CalibrationScopeDecisionResult:
    if not template_path.is_file():
        raise CalibrationScopeDecisionError(
            f"calibration scope decision template not found: {template_path}"
        )
    content = template_path.read_text(encoding="utf-8")
    if not content.strip():
        raise CalibrationScopeDecisionError("calibration scope decision template is empty")

    missing_headings = _missing(REQUIRED_HEADINGS, content)
    if missing_headings:
        raise CalibrationScopeDecisionError(
            "missing heading(s): " + ", ".join(missing_headings)
        )

    missing_fields = _missing(REQUIRED_FIELDS, content)
    if missing_fields:
        raise CalibrationScopeDecisionError(
            "missing decision field(s): " + ", ".join(missing_fields)
        )

    if "completed copy" not in content or "production promotion evidence" not in content:
        raise CalibrationScopeDecisionError(
            "template must tell reviewers where the completed copy is stored"
        )

    return CalibrationScopeDecisionResult(
        headings=len(REQUIRED_HEADINGS),
        fields=len(REQUIRED_FIELDS),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the RetOS calibration scope decision evidence template."
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=DEFAULT_TEMPLATE,
        help="Path to docs/releases/evidence/calibration-scope-decision-template.md.",
    )
    args = parser.parse_args()
    try:
        result = validate_calibration_scope_decision(args.template)
    except CalibrationScopeDecisionError as exc:
        print(f"Calibration scope decision failed: {exc}", file=sys.stderr)
        return 1
    print(
        "Calibration scope decision OK: "
        f"{result.headings} heading(s), {result.fields} decision field(s) verified."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
