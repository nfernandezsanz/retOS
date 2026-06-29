#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
MAKEFILE = ROOT / "Makefile"

REQUIRED_HEADINGS = (
    "# RetOS",
    "## First Minute",
    "## Local Quick Start",
    "## Local Troubleshooting",
    "## Local Audit Handoff",
    "## Current Status",
    "## What You Can Do Today",
    "## Development Model",
    "## Quality Gates",
)

REQUIRED_PHRASES = (
    "Action pills",
    "run-make%20local--demo",
    "open-react%20console",
    "audit-make%20auditor--handoff--check",
    "verify-local%20quality%20gates",
    "release-human%20promotion%20pack",
    "coverage-95.42%25%20total%20%7C%2090.75%25%20branch",
    "stability-pre--alpha",
    "Product maturity",
    "Backend coverage",
    "Production status",
    "Not production-promoted",
    "make local-demo",
    "make local-status",
    "make local-logs",
    "make bootstrap-env",
    "docker compose up --build",
    "make docker-seed-demo",
    "curl --fail http://localhost:8000/readyz",
    "make docker-down",
    "make env-security-check",
    "make visual-audit-check",
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

REQUIRED_MAKE_TARGETS = (
    "check",
    "bootstrap-env",
    "local-demo",
    "local-status",
    "local-logs",
    "local-acceptance",
    "auditor-handoff-check",
    "audit-bundle-check",
    "frontend-e2e",
    "frontend-visual-audit",
    "docker-smoke",
    "production-preflight",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"README usability failed: {message}")


def make_targets(makefile_path: Path = MAKEFILE) -> set[str]:
    require(
        makefile_path.is_file() and makefile_path.stat().st_size > 0,
        "missing or empty Makefile",
    )
    targets: set[str] = set()
    target_pattern = re.compile(r"^([A-Za-z0-9_.-]+):(?:\s|$)")
    for line in makefile_path.read_text(encoding="utf-8").splitlines():
        match = target_pattern.match(line)
        if match and not line.startswith("."):
            targets.add(match.group(1))
    return targets


def validate_readme(readme_path: Path = README, makefile_path: Path = MAKEFILE) -> None:
    require(
        readme_path.is_file() and readme_path.stat().st_size > 0,
        "missing or empty README.md",
    )
    content = readme_path.read_text(encoding="utf-8")
    targets = make_targets(makefile_path)

    for heading in REQUIRED_HEADINGS:
        require(heading in content, f"missing heading: {heading}")

    for phrase in REQUIRED_PHRASES:
        require(phrase in content, f"missing phrase: {phrase}")

    for row in FIRST_MINUTE_ROWS:
        require(row in content, f"First Minute table missing row: {row}")

    for target in REQUIRED_MAKE_TARGETS:
        require(
            target in targets,
            f"README command references missing Make target: {target}",
        )
        require(
            f"make {target}" in content,
            f"README missing command for Make target: {target}",
        )

    require(
        content.index("## First Minute") < content.index("## Local Quick Start"),
        "First Minute must appear before Local Quick Start",
    )
    require(
        content.index("## Local Quick Start")
        < content.index("## Local Troubleshooting"),
        "Local Troubleshooting must appear after Local Quick Start",
    )
    require(
        content.index("## Local Troubleshooting")
        < content.index("## Local Audit Handoff"),
        "Local Troubleshooting must appear before Local Audit Handoff",
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
