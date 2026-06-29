#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TRACKER = ROOT / "planning/04-process-tracker.md"

EXPECTED_COLUMNS = [
    "Phase",
    "Status",
    "Implementation",
    "Tests",
    "Coverage",
    "Auditability",
    "Docs",
    "Risks",
]
EXPECTED_PHASES = [
    "0 - Open Source Bootstrap",
    "1 - Core Domain And Persistence",
    "2 - Ingestion, OCR, And BM25",
    "3 - Deep Agents Runtime",
    "4 - Product UI",
    "5 - Evals",
    "6 - Alpha Release",
]
ALLOWED_STATUSES = {"Not started", "In progress", "Blocked", "In review", "Complete"}
FORBIDDEN_PLACEHOLDERS = {"", "todo", "tbd", "n/a", "none", "-"}


@dataclass(frozen=True)
class TrackerRow:
    phase: str
    status: str
    implementation: str
    tests: str
    coverage: str
    auditability: str
    docs: str
    risks: str


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"Process tracker failed: {message}")


def split_markdown_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def parse_tracker(path: Path) -> list[TrackerRow]:
    content = path.read_text(encoding="utf-8")
    require("# Process Tracker" in content, "missing title")
    require("Last updated:" in content, "missing last updated marker")
    require("Status values:" in content, "missing status value legend")

    lines = content.splitlines()
    header_index = next(
        (
            index
            for index, line in enumerate(lines)
            if split_markdown_row(line) == EXPECTED_COLUMNS
        ),
        None,
    )
    require(header_index is not None, "missing phase table header")
    rows: list[TrackerRow] = []
    for line in lines[header_index + 2 :]:
        if not line.startswith("|"):
            break
        cells = split_markdown_row(line)
        require(len(cells) == len(EXPECTED_COLUMNS), f"malformed row: {line}")
        rows.append(TrackerRow(*cells))
    return rows


def has_placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized in FORBIDDEN_PLACEHOLDERS or "todo" in normalized


def validate_tracker(path: Path = DEFAULT_TRACKER) -> None:
    require(path.is_file() and path.stat().st_size > 0, f"missing tracker: {path}")
    rows = parse_tracker(path)
    phases = [row.phase for row in rows]
    require(
        phases == EXPECTED_PHASES,
        "phase table must contain phases 0 through 6 in order",
    )

    for row in rows:
        require(row.status in ALLOWED_STATUSES, f"{row.phase} has invalid status")
        for column, value in (
            ("Implementation", row.implementation),
            ("Tests", row.tests),
            ("Coverage", row.coverage),
            ("Auditability", row.auditability),
            ("Docs", row.docs),
            ("Risks", row.risks),
        ):
            require(not has_placeholder(value), f"{row.phase} has placeholder {column}")
        require("95.42%" in row.coverage, f"{row.phase} must record total coverage")
        require("90.75%" in row.coverage, f"{row.phase} must record branch coverage")
        require(
            "journal" in row.auditability.lower()
            or "audit" in row.auditability.lower(),
            f"{row.phase} must explain journal or audit evidence",
        )

    by_phase = {row.phase: row for row in rows}
    require(
        "make local-smoke" in by_phase["0 - Open Source Bootstrap"].auditability,
        "phase 0 must keep local smoke evidence visible",
    )
    require(
        "Deep Agents" in by_phase["3 - Deep Agents Runtime"].implementation
        and "harness" in by_phase["3 - Deep Agents Runtime"].implementation,
        "phase 3 must keep Deep Agents harness scope visible",
    )
    require(
        "tooltip" in by_phase["4 - Product UI"].implementation.lower()
        and "frontend-visual-audit" in by_phase["4 - Product UI"].tests,
        "phase 4 must keep tooltip and visual audit evidence visible",
    )
    require(
        "calibration" in by_phase["5 - Evals"].implementation.lower()
        and "Public calibration slices beyond 200 records"
        in by_phase["5 - Evals"].risks,
        "phase 5 must keep bounded calibration risk visible",
    )
    require(
        "make local-acceptance" in by_phase["6 - Alpha Release"].tests
        and "promotion decision checklist"
        in by_phase["6 - Alpha Release"].auditability,
        "phase 6 must keep local acceptance and promotion checklist evidence visible",
    )
    require(
        "Final release promotion still requires" in by_phase["6 - Alpha Release"].risks,
        "phase 6 must keep external promotion blockers visible",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the RetOS process tracker.")
    parser.add_argument(
        "--tracker",
        type=Path,
        default=DEFAULT_TRACKER,
        help="Path to planning/04-process-tracker.md.",
    )
    args = parser.parse_args()
    tracker = args.tracker if args.tracker.is_absolute() else ROOT / args.tracker
    validate_tracker(tracker)
    print("Process tracker OK: phases, evidence, coverage, and blockers are aligned.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
