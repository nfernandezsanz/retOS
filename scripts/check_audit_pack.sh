#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
from __future__ import annotations

from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"Audit pack failed: {message}")


paths = {
    "audit_pack": Path("docs/production-readiness.md"),
    "readme": Path("README.md"),
    "operations": Path("docs/operations.md"),
    "release_process": Path("docs/release-process.md"),
    "tracker": Path("planning/04-process-tracker.md"),
    "release_note": Path("docs/releases/2026.06.28-alpha.1.md"),
    "ci": Path(".github/workflows/ci.yml"),
    "ci_status_script": Path("scripts/check_ci_status.sh"),
    "dependency_audit_script": Path("scripts/check_dependency_audit.sh"),
}

for name, path in paths.items():
    require(path.is_file() and path.stat().st_size > 0, f"missing or empty {name}: {path}")

audit_pack = paths["audit_pack"].read_text(encoding="utf-8")
readme = paths["readme"].read_text(encoding="utf-8")
operations = paths["operations"].read_text(encoding="utf-8")
release_process = paths["release_process"].read_text(encoding="utf-8")
tracker = paths["tracker"].read_text(encoding="utf-8")
release_note = paths["release_note"].read_text(encoding="utf-8")
ci = paths["ci"].read_text(encoding="utf-8")

for heading in (
    "## Current Verdict",
    "## Auditor Review Order",
    "## Required Local Evidence",
    "## Promotion Blockers",
    "## Production Pilot Acceptance Checklist",
    "## Evidence Locations",
):
    require(heading in audit_pack, f"docs/production-readiness.md missing {heading}")

for phrase in (
    "RetOS is not production-promoted yet",
    "make check",
    "make integration",
    "make frontend-test",
    "make frontend-e2e",
    "make brand-check",
    "make docker-smoke",
    "make dependency-audit",
    "make ci-status-check",
    "make production-preflight",
    "scripts/check_release_readiness.sh",
    "scripts/check_audit_pack.sh",
    "scripts/check_branding_assets.sh",
    "scripts/check_dependency_audit.sh",
    "scripts/check_ci_status.sh",
    "pip-audit",
    "npm audit --audit-level=high",
    "GHCR",
    "SBOM/provenance",
    "Cosign",
    "Branch coverage",
    "95.20% total",
    "90.44% branch-only",
    "RETOS_ALLOW_PAID_LLM=false",
    "RETOS_OLLAMA_MODEL=gemma4",
    "/audit/export",
    "Branding assets",
):
    require(phrase in audit_pack, f"docs/production-readiness.md missing evidence phrase: {phrase}")

for linked_doc, content in (
    ("README.md", readme),
    ("docs/operations.md", operations),
    ("docs/release-process.md", release_process),
):
    require(
        "docs/production-readiness.md" in content or "production-readiness.md" in content,
        f"{linked_doc} must link the production readiness audit pack",
    )

require(
    "Product maturity is pre-alpha" in release_note,
    "release note must keep maturity limitation explicit",
)
require(
    "Publishing evidence still required" in release_note,
    "release note must keep publish evidence blockers explicit",
)
require(
    "90.44% branch" in readme,
    "README must record current branch coverage evidence",
)
require(
    "make ci-status-check" in release_process,
    "release process must require current HEAD CI verification",
)
require(
    "make dependency-audit" in release_process,
    "release process must require dependency advisory verification",
)
require(
    "Final release promotion still requires" in tracker,
    "process tracker must keep final release blockers visible",
)
require(
    "pip_audit" in ci and "npm audit --audit-level=high" in ci,
    "CI must run Python and Node dependency audits",
)
require(
    "check_audit_pack.sh" in ci,
    "CI must run the audit pack guard",
)
require(
    "check_production_preflight.sh" in ci,
    "CI must run the production preflight guard",
)

print("Audit pack OK: production readiness evidence, blockers, and links are aligned.")
PY
