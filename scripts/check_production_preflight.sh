#!/usr/bin/env bash
set -euo pipefail

scripts/check_release_readiness.sh >/dev/null
scripts/check_ci_workflow.sh >/dev/null
python3 scripts/check_readme_usability.py >/dev/null
python3 scripts/check_visual_review.py >/dev/null
scripts/check_audit_pack.sh >/dev/null
scripts/check_release_notes.sh >/dev/null
scripts/check_versioned_release_notes.sh >/dev/null
scripts/check_release_workflow.sh >/dev/null
scripts/check_branding_assets.sh >/dev/null

python3 - <<'PY'
from __future__ import annotations

from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"Production preflight failed: {message}")


audit_pack = Path("docs/production-readiness.md").read_text(encoding="utf-8")
branding = Path("docs/branding.md").read_text(encoding="utf-8")
release_note = Path("docs/releases/2026.06.28-alpha.1.md").read_text(encoding="utf-8")
tracker = Path("planning/04-process-tracker.md").read_text(encoding="utf-8")
ci = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
release_workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")

for heading in (
    "## Machine-Verified Preflight",
    "## External Promotion Evidence",
    "## Promotion Blockers",
    "## Production Pilot Acceptance Checklist",
):
    require(heading in audit_pack, f"production readiness pack missing {heading}")

for command in (
    "make check",
    "make integration",
    "make frontend-test",
    "make frontend-e2e",
    "make frontend-visual-audit",
    "make visual-review-check",
    "docker compose --env-file .env.example config",
    "docker compose --dry-run build",
    "make docker-smoke",
    "make release-check",
    "make dependency-audit",
    "make security-policy-check",
    "make ignore-hygiene-check",
    "make operations-runbook-check",
    "make auditor-static-check",
    "make audit-manifest-check",
    "make audit-manifest",
    "make ci-status-check",
    "make production-preflight",
):
    require(command in audit_pack, f"production readiness pack missing command: {command}")

for external_item in (
    "GHCR digests",
    "SBOM/provenance",
    "Cosign signature",
    "Human security review",
):
    require(external_item in audit_pack, f"production readiness pack missing external evidence: {external_item}")

require(
    "Branch coverage below final target" not in audit_pack,
    "branch coverage blocker must stay removed after 90% branch ratchet",
)
require(
    "90.78% branch" in audit_pack and "95.43% total" in audit_pack,
    "coverage evidence must match the current README/release note ratchet",
)
require(
    "739 pytest cases" in audit_pack,
    "production readiness pack must record the current backend pytest case count",
)
for unique_gate in (
    "| Backend quality |",
    "| Security policy |",
    "| README usability |",
    "| Auditor evidence matrix |",
):
    require(
        audit_pack.count(unique_gate) == 1,
        f"production readiness pack must contain exactly one row for {unique_gate}",
    )
require(
    "Latest Visual Audit" in branding and "Desktop 1440x900" in branding and "Mobile 390x844" in branding,
    "branding guide must keep current visual audit evidence",
)
require(
    "Publishing evidence still required" in release_note,
    "release note must keep external publish evidence pending until the release workflow runs",
)
require(
    "Final release promotion still requires" in tracker,
    "process tracker must keep final release blockers visible",
)
require(
    "make local-acceptance" in tracker,
    "process tracker must keep the local acceptance gate visible",
)
require(
    "promotion decision checklist" in tracker,
    "process tracker must keep the audit handoff checklist visible",
)
require(
    "check_production_preflight.sh" in ci,
    "CI must run the production preflight guard",
)
require(
    "make production-preflight" in release_workflow,
    "release workflow must run the production preflight before publishing",
)

print("Production preflight OK: local evidence, branding, release docs, and external blockers are aligned.")
PY
