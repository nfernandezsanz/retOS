#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
from __future__ import annotations

from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"Release notes failed: {message}")


changelog_path = Path("CHANGELOG.md")
release_process_path = Path("docs/release-process.md")
operations_path = Path("docs/operations.md")
readme_path = Path("README.md")
versioned_release_path = Path("docs/releases/2026.06.28-alpha.1.md")

for path in (changelog_path, release_process_path, versioned_release_path):
    require(path.is_file() and path.stat().st_size > 0, f"missing or empty {path}")

changelog = changelog_path.read_text(encoding="utf-8")
release_process = release_process_path.read_text(encoding="utf-8")
operations = operations_path.read_text(encoding="utf-8")
readme = readme_path.read_text(encoding="utf-8")

require("# Changelog" in changelog, "CHANGELOG.md must have a title")
require("## Unreleased" in changelog, "CHANGELOG.md must keep an Unreleased section")
for heading in ("### Added", "### Changed", "### Security"):
    require(heading in changelog, f"CHANGELOG.md missing {heading}")

for phrase in (
    "Release Note Checklist",
    "Migration notes",
    "Validation evidence",
    "rollback guidance",
    "make local-acceptance",
    "promotion decision checklist",
):
    require(phrase in changelog, f"CHANGELOG.md missing release note guidance: {phrase}")

for heading in (
    "## Versioning",
    "## Release Candidate Checklist",
    "## Release Notes Template",
    "## Audit Expectations",
):
    require(heading in release_process, f"docs/release-process.md missing {heading}")

for phrase in (
    "RETOS_RELEASE_VERSION",
    "RETOS_IMAGE_TAG",
    "RETOS_REVISION",
    "scripts/check_image_metadata.sh",
    "make release-evidence-check",
    "make local-acceptance",
    "make docker-smoke",
    "make auditor-static-check",
    "make frontend-visual-audit",
    "docker compose --env-file .env.example config",
    "docker compose --dry-run build",
    "Visual audit screenshots",
    "Compose config",
    "Docker build dry run",
    "Production promotion template",
    "Backend coverage",
    "Migration Notes",
    "Rollback",
):
    require(phrase in release_process, f"docs/release-process.md missing {phrase}")

require(
    "docs/release-process.md" in readme,
    "README.md must link the release process",
)
require(
    "CHANGELOG.md" in readme,
    "README.md must link the changelog",
)
require(
    "docs/release-process.md" in operations,
    "docs/operations.md must point release operators at the release process",
)

print("Release notes OK: changelog, release process, and docs links are aligned.")
PY
