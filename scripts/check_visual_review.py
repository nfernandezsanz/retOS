#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = ROOT / "docs/releases/evidence/visual-review-template.md"

REQUIRED_HEADINGS = (
    "# Visual Review Evidence Template",
    "## Candidate",
    "## Machine Evidence",
    "## Screenshot Evidence",
    "## Review Scope",
    "## Findings",
    "## Decision",
)

REQUIRED_GATES = (
    "make frontend-test",
    "make frontend-e2e",
    "make frontend-visual-audit",
    "make visual-audit-check",
    "make brand-check",
    "make readme-check",
)

REQUIRED_FIELDS = (
    "Release version",
    "Commit SHA",
    "GitHub Actions run",
    "Target environment",
    "Reviewer",
    "Review date",
    "Visual audit manifest",
    "frontend/visual-audit/manifest.json",
    "Desktop screenshot",
    "frontend/visual-audit/retos-console-desktop.png",
    "Desktop viewport",
    "1440x900",
    "Desktop SHA-256",
    "Mobile screenshot",
    "frontend/visual-audit/retos-console-mobile.png",
    "Mobile viewport",
    "390x844",
    "Mobile SHA-256",
    "Remote artifact",
    "retos-visual-audit-<commit>",
    "Overview first screen reviewed",
    "Documents workflow reviewed",
    "Queries workflow reviewed",
    "Evals workflow reviewed",
    "Audit workflow reviewed",
    "Admin workflow reviewed",
    "Tooltip hover/focus behavior reviewed",
    "Keyboard focus and skip link reviewed",
    "Mobile overflow reviewed",
    "Desktop overflow reviewed",
    "Reduced motion reviewed",
    "Brand mark, palette, and project card reviewed",
    "Visual defects found",
    "Accessibility concerns found",
    "Responsiveness concerns found",
    "Accepted visual risks",
    "Follow-up issue links",
    "Visual review decision",
    "Reviewer sign-off",
    "Promotion impact",
)


class VisualReviewError(RuntimeError):
    pass


@dataclass(frozen=True)
class VisualReviewResult:
    headings: int
    gates: int
    fields: int


def _missing(required: tuple[str, ...], content: str) -> list[str]:
    return [item for item in required if item not in content]


def validate_visual_review(
    template_path: Path = DEFAULT_TEMPLATE,
) -> VisualReviewResult:
    if not template_path.is_file():
        raise VisualReviewError(f"visual review template not found: {template_path}")
    content = template_path.read_text(encoding="utf-8")
    if not content.strip():
        raise VisualReviewError("visual review template is empty")

    missing_headings = _missing(REQUIRED_HEADINGS, content)
    if missing_headings:
        raise VisualReviewError("missing heading(s): " + ", ".join(missing_headings))

    missing_gates = _missing(REQUIRED_GATES, content)
    if missing_gates:
        raise VisualReviewError("missing machine gate(s): " + ", ".join(missing_gates))

    missing_fields = _missing(REQUIRED_FIELDS, content)
    if missing_fields:
        raise VisualReviewError("missing review field(s): " + ", ".join(missing_fields))

    normalized = " ".join(content.split())
    if (
        "completed copy" not in normalized
        or "production promotion evidence" not in normalized
    ):
        raise VisualReviewError(
            "template must tell reviewers where the completed copy is stored"
        )

    return VisualReviewResult(
        headings=len(REQUIRED_HEADINGS),
        gates=len(REQUIRED_GATES),
        fields=len(REQUIRED_FIELDS),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the RetOS visual review evidence template."
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=DEFAULT_TEMPLATE,
        help="Path to docs/releases/evidence/visual-review-template.md.",
    )
    args = parser.parse_args()
    try:
        result = validate_visual_review(args.template)
    except VisualReviewError as exc:
        print(f"Visual review failed: {exc}", file=sys.stderr)
        return 1
    print(
        "Visual review OK: "
        f"{result.headings} heading(s), {result.gates} machine gate(s), "
        f"{result.fields} review field(s) verified."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
