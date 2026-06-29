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
    "calibration_scope_template": Path("docs/releases/evidence/calibration-scope-decision-template.md"),
    "backup_restore_drill_template": Path("docs/releases/evidence/backup-restore-drill-template.md"),
    "target_security_review_template": Path("docs/releases/evidence/target-security-review-template.md"),
    "promotion_template": Path("docs/releases/evidence/production-promotion-template.md"),
    "ci": Path(".github/workflows/ci.yml"),
    "ci_status_script": Path("scripts/check_ci_status.sh"),
    "dependency_audit_script": Path("scripts/check_dependency_audit.sh"),
    "security_policy_script": Path("scripts/check_security_policy.sh"),
    "ignore_hygiene_script": Path("scripts/check_ignore_hygiene.sh"),
    "calibration_scope_script": Path("scripts/check_calibration_scope_decision.py"),
    "backup_restore_drill_script": Path("scripts/check_backup_restore_drill.py"),
    "target_security_review_script": Path("scripts/check_target_security_review.py"),
    "promotion_template_script": Path("scripts/check_promotion_template.py"),
    "security_policy": Path("SECURITY.md"),
    "audit_manifest_script": Path("scripts/export_audit_manifest.py"),
}

for name, path in paths.items():
    require(path.is_file() and path.stat().st_size > 0, f"missing or empty {name}: {path}")

audit_pack = paths["audit_pack"].read_text(encoding="utf-8")
readme = paths["readme"].read_text(encoding="utf-8")
operations = paths["operations"].read_text(encoding="utf-8")
release_process = paths["release_process"].read_text(encoding="utf-8")
tracker = paths["tracker"].read_text(encoding="utf-8")
release_note = paths["release_note"].read_text(encoding="utf-8")
promotion_template = paths["promotion_template"].read_text(encoding="utf-8")
ci = paths["ci"].read_text(encoding="utf-8")
audit_manifest_script = paths["audit_manifest_script"].read_text(encoding="utf-8")

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
    "make local-acceptance",
    "make check",
    "make integration",
    "make frontend-test",
    "make frontend-e2e",
    "make frontend-visual-audit",
    "docker compose --env-file .env.example config",
    "docker compose --dry-run build",
    "make brand-check",
    "make docker-smoke",
    "make dependency-audit",
    "make security-policy-check",
    "make target-security-review-check",
    "make calibration-scope-decision-check",
    "make promotion-template-check",
    "make ignore-hygiene-check",
    "make operations-runbook-check",
    "make backup-restore-drill-check",
    "make auditor-static-check",
    "make auditor-handoff-check",
    "make audit-manifest-check",
    "make audit-manifest",
    "make audit-bundle",
    "make audit-bundle-check",
    "make audit-export-check",
    "make ci-status-check",
    "make production-preflight",
    "make release-evidence-check",
    "scripts/check_release_readiness.sh",
    "scripts/check_audit_pack.sh",
    "scripts/check_published_release_evidence.sh",
    "scripts/check_branding_assets.sh",
    "scripts/check_dependency_audit.sh",
    "scripts/check_security_policy.sh",
    "scripts/check_target_security_review.py",
    "scripts/check_calibration_scope_decision.py",
    "scripts/check_ignore_hygiene.sh",
    "scripts/check_backup_restore_drill.py",
    "scripts/check_promotion_template.py",
    "scripts/check_operations_runbook.sh",
    "scripts/check_audit_export.py",
    "scripts/check_ci_status.sh",
    "pip-audit",
    "npm audit --audit-level=high",
    "GHCR",
    "SBOM/provenance",
    "Cosign",
    "tag-to-digest resolution",
    "Branch coverage",
    "95.39% total",
    "90.73% branch-only",
    "RETOS_ALLOW_PAID_LLM=false",
    "RETOS_OLLAMA_MODEL=gemma4",
    "/audit/export",
    "Visual audit screenshots",
    "Branding assets",
    "SECURITY.md",
    ".dockerignore",
    "docs/releases/evidence/calibration-scope-decision-template.md",
    "docs/releases/evidence/backup-restore-drill-template.md",
    "docs/releases/evidence/target-security-review-template.md",
    "docs/releases/evidence/production-promotion-template.md",
    "JSON handoff",
    "coverage evidence derived from `backend/coverage.json`",
    "Promotion decision checklist",
    "generation context",
    "in-run snapshot",
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
    "Current draft evidence commit:" in release_note and "make ci-status-check" in release_note,
    "release note must distinguish current draft evidence from final tag evidence",
)
require(
    "audit-evidence" in release_note and "retos-audit-manifest-" in release_note,
    "release note must record final CI audit-evidence and manifest artifact evidence",
)
require(
    "in-run snapshot" in release_note,
    "release note must explain CI-generated audit manifests are in-run snapshots",
)
require(
    "Publishing evidence still required" in release_note,
    "release note must keep publish evidence blockers explicit",
)
require(
    "90.73% branch" in readme,
    "README must record current branch coverage evidence",
)
require(
    "make ci-status-check" in release_process,
    "release process must require current HEAD CI verification",
)
require(
    "make auditor-static-check" in release_process and "make frontend-visual-audit" in release_process,
    "release process must require auditor static and visual audit evidence",
)
require(
    "make auditor-handoff-check" in release_process and "make auditor-handoff-check" in readme,
    "release process and README must document the auditor handoff command",
)
require(
    "make local-acceptance" in readme
    and "make local-acceptance" in release_process
    and "make local-acceptance" in audit_pack,
    "README, release process, and production readiness pack must document the local acceptance gate",
)
require(
    "promotion decision checklist" in readme
    and "promotion decision checklist" in release_process
    and "Promotion decision checklist" in audit_pack,
    "README, release process, and production readiness pack must document the generated promotion checklist",
)
require(
    "It does not replace tag publishing" in release_process,
    "release process must keep auditor handoff scoped below final release promotion",
)
require(
    "make dependency-audit" in release_process,
    "release process must require dependency advisory verification",
)
require(
    "make audit-manifest" in release_process and "scripts/export_audit_manifest.py" in audit_pack,
    "release process and audit pack must document the audit manifest exporter",
)
require(
    "make audit-manifest-check" in release_process and "scripts/check_audit_manifest.py" in audit_pack,
    "release process and audit pack must document the audit manifest schema checker",
)
require(
    "make audit-bundle" in release_process
    and "scripts/export_audit_bundle.py" in audit_pack
    and "scripts/check_audit_bundle.py" in audit_pack,
    "release process and audit pack must document the audit bundle exporter and checker",
)
for phrase in (
    "generation_context",
    "generated_for_current_github_run",
    "post_run_ci_validation_required",
    "post_run_ci_validation_command",
    "coverage_targets()",
    "backend/coverage.json",
    "make audit-manifest-check",
):
    require(phrase in audit_manifest_script, f"audit manifest must record CI generation semantics: {phrase}")
require(
    "production-promotion-template.md" in operations and "production-promotion-template.md" in release_process,
    "operations and release process must link the promotion evidence template",
)
require(
    "target-security-review-template.md" in readme
    and "target-security-review-template.md" in release_process
    and "target-security-review-template.md" in paths["security_policy"].read_text(encoding="utf-8"),
    "README, release process, and SECURITY.md must link the target security review template",
)
require(
    "calibration-scope-decision-template.md" in readme
    and "calibration-scope-decision-template.md" in operations
    and "calibration-scope-decision-template.md" in release_process
    and "calibration-scope-decision-template.md" in audit_pack,
    "README, operations, release process, and audit pack must link the calibration scope decision template",
)
for heading in (
    "## Machine Evidence",
    "## Release Provenance",
    "## Visual Review",
    "## Backup And Restore Rehearsal",
    "## Security Review",
    "## Rollback",
    "## Decision",
):
    require(heading in promotion_template, f"promotion evidence template missing {heading}")
require(
    "Immutable release tag" in promotion_template,
    "promotion evidence template must record the immutable release tag",
)
require(
    "make local-acceptance" in promotion_template,
    "promotion evidence template must require the local acceptance gate",
)
for gate in (
    "make env-security-check",
    "make target-security-review-check",
    "make calibration-scope-decision-check",
    "make visual-audit-check",
    "make promotion-template-check",
):
    require(
        gate in promotion_template,
        f"promotion evidence template must require {gate}",
    )
require(
    "Final release promotion still requires" in tracker,
    "process tracker must keep final release blockers visible",
)
require(
    "make local-acceptance" in tracker and "promotion decision checklist" in tracker,
    "process tracker must keep local acceptance and audit checklist evidence visible",
)
for phrase in (
    "Desktop visual audit PNG reviewed",
    "Mobile visual audit PNG reviewed",
    "`make visual-audit-check` output",
    "Visual review decision",
    "UI issues accepted or filed",
):
    require(
        phrase in promotion_template,
        f"promotion evidence template missing visual review field: {phrase}",
    )
require(
    "`make env-security-check` output" in promotion_template,
    "promotion evidence template must record env-security-check output",
)
require(
    "Calibration scope decision template completed" in promotion_template,
    "promotion evidence template must record calibration scope decision completion",
)
require(
    "make frontend-visual-audit" in tracker and "visual audit evidence" in tracker,
    "process tracker must keep visual audit promotion evidence visible",
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
require(
    "make auditor-static-check" in ci,
    "CI must run the consolidated auditor static pack",
)
for phrase in (
    "artifacts?per_page=50",
    "retos-backend-coverage-{sha}",
    "retos-visual-audit-{sha}",
    "retos-audit-manifest-{sha}",
    "retos-audit-handoff-{sha}",
    "expired_artifacts",
    "size_in_bytes",
    "empty_artifacts",
):
    require(phrase in paths["ci_status_script"].read_text(encoding="utf-8"), f"CI status check must validate required artifacts: {phrase}")
for phrase in (
    "audit-evidence:",
    "needs:",
    "- backend",
    "- frontend",
    "- docker",
    "actions/download-artifact@v4",
    "retos-backend-coverage-${{ github.sha }}",
    "cp /tmp/retos-backend-coverage/coverage.json backend/coverage.json",
    "make audit-manifest OUTPUT=retos-audit-manifest.json",
    "make audit-handoff-report MANIFEST=retos-audit-manifest.json OUTPUT=retos-audit-handoff.md",
    "retos-audit-manifest-${{ github.sha }}",
    "retos-audit-handoff-${{ github.sha }}",
    "path: retos-audit-manifest.json",
    "path: retos-audit-handoff.md",
):
    require(phrase in ci, f"CI must publish audit manifest evidence: {phrase}")

print("Audit pack OK: production readiness evidence, blockers, and links are aligned.")
PY
