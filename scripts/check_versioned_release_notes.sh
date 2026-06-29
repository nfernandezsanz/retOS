#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
from __future__ import annotations

import re
from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"Versioned release notes failed: {message}")


release_dir = Path("docs/releases")
index_path = release_dir / "README.md"
project_readme_path = Path("README.md")
release_files = sorted(release_dir.glob("*.md"))
versioned_files = [path for path in release_files if path.name != "README.md"]

require(index_path.is_file() and index_path.stat().st_size > 0, "docs/releases/README.md is required")
require(project_readme_path.is_file(), "README.md is required")
require(versioned_files, "at least one versioned release note is required")

index = index_path.read_text(encoding="utf-8")
project_readme = project_readme_path.read_text(encoding="utf-8")
coverage_match = re.search(r"Backend coverage \| ([0-9]+\.[0-9]+%)", project_readme)
require(coverage_match is not None, "README.md must record backend coverage evidence")
current_backend_coverage = coverage_match.group(1)
for phrase in (
    "versioned release notes",
    "CHANGELOG.md",
    "SBOM/provenance",
    "Cosign",
):
    require(phrase in index, f"docs/releases/README.md missing {phrase}")

required_sections = (
    "## Highlights",
    "## Migration Notes",
    "## Compatibility",
    "## Security",
    "## Validation Evidence",
    "## Known Limitations",
    "## Rollback",
)

required_phrases = (
    "Current draft evidence commit:",
    "make ci-status-check",
    "exact immutable release tag commit must",
    "Images:",
    "retos-backend",
    "retos-web",
    "Backend coverage",
    "GHCR publishing",
    "SBOM/provenance",
    "Cosign signatures",
    "signature verification",
    "make release-evidence-check",
    "make frontend-visual-audit",
    "make audit-manifest",
    "Audit handoff manifest",
    "Audit handoff report",
    "retos-audit-manifest-",
    "retos-audit-handoff-",
    "audit-evidence",
    "Rollback",
)

version_pattern = re.compile(r"^\d{4}\.\d{2}\.\d{2}(?:[-._+a-zA-Z0-9]+)?\.md$")

for path in versioned_files:
    require(version_pattern.match(path.name), f"{path} must be named like 2026.06.28-alpha.1.md")
    content = path.read_text(encoding="utf-8")
    require(content.startswith("# RetOS "), f"{path} must start with a RetOS title")
    for section in required_sections:
        require(section in content, f"{path} missing {section}")
    for phrase in required_phrases:
        require(phrase in content, f"{path} missing {phrase}")
    require("Pending until" in content, f"{path} must state pending publish evidence while pre-release")
    require(
        current_backend_coverage in content,
        f"{path} must record current backend coverage evidence",
    )
    evidence_match = re.search(
        r"Current draft evidence commit: `([0-9a-f]{7,40})`",
        content,
    )
    require(
        evidence_match is not None,
        f"{path} must record a concrete draft evidence commit SHA",
    )
    require(
        f"retos-audit-manifest-{evidence_match.group(1)}" in content,
        f"{path} must align the audit manifest artifact with the draft evidence commit",
    )
    require(
        f"retos-audit-handoff-{evidence_match.group(1)}" in content,
        f"{path} must align the audit handoff artifact with the draft evidence commit",
    )

print(f"Versioned release notes OK: {len(versioned_files)} release note(s) validated.")
PY
