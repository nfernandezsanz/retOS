#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"

REQUIRED_HEADINGS = (
    "# RetOS",
    "## First Minute",
    "## Local Quick Start",
    "## Local Audit Handoff",
    "## Current Status",
    "## What You Can Do Today",
    "## Development Model",
    "## Quality Gates",
)

REQUIRED_PHRASES = (
    "Action pills",
    "run-docker%20compose%20up%20--build",
    "open-react%20console",
    "audit-make%20auditor--handoff--check",
    "verify-local%20quality%20gates",
    "release-human%20promotion%20pack",
    "coverage-95.43%25%20total%20%7C%2090.78%25%20branch",
    "stability-pre--alpha",
    "Product maturity",
    "Backend coverage",
    "Production status",
    "Not production-promoted",
    "docker compose up --build",
    "make docker-seed-demo",
    "make auditor-handoff-check",
    "make local-acceptance",
    "make check",
    "make frontend-e2e",
    "make docker-smoke",
    "Codex and Claude",
    "limited human interaction",
    "planning/",
    "docs/adr/",
    "no paid-provider calls in tests",
)

FIRST_MINUTE_ROWS = (
    "| Run the product |",
    "| See useful data |",
    "| Trust the evidence |",
    "| Judge readiness |",
    "| Work with agents |",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"README usability failed: {message}")


def validate_readme(readme_path: Path = README) -> None:
    require(
        readme_path.is_file() and readme_path.stat().st_size > 0,
        "missing or empty README.md",
    )
    content = readme_path.read_text(encoding="utf-8")

    for heading in REQUIRED_HEADINGS:
        require(heading in content, f"missing heading: {heading}")

    for phrase in REQUIRED_PHRASES:
        require(phrase in content, f"missing phrase: {phrase}")

    for row in FIRST_MINUTE_ROWS:
        require(row in content, f"First Minute table missing row: {row}")

    require(
        content.index("## First Minute") < content.index("## Local Quick Start"),
        "First Minute must appear before Local Quick Start",
    )
    require(
        content.index("## Current Status") < content.index("## What You Can Do Today"),
        "Current Status must appear before workflow details",
    )


def main() -> None:
    validate_readme()
    print(
        "README usability OK: onboarding, status, local actions, and agent workflow are visible."
    )


if __name__ == "__main__":
    main()
