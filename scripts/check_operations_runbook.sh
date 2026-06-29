#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
from __future__ import annotations

from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"Operations runbook failed: {message}")


operations = Path("docs/operations.md").read_text(encoding="utf-8")
production_readiness = Path("docs/production-readiness.md").read_text(encoding="utf-8")
promotion_template = Path("docs/releases/evidence/production-promotion-template.md").read_text(
    encoding="utf-8"
)
drill_template = Path("docs/releases/evidence/backup-restore-drill-template.md").read_text(
    encoding="utf-8"
)
target_security_template = Path(
    "docs/releases/evidence/target-security-review-template.md"
).read_text(encoding="utf-8")
calibration_scope_template = Path(
    "docs/releases/evidence/calibration-scope-decision-template.md"
).read_text(encoding="utf-8")
gitignore = Path(".gitignore").read_text(encoding="utf-8")
dockerignore = Path(".dockerignore").read_text(encoding="utf-8")
api_smoke = Path("backend/scripts/smoke_api.py").read_text(encoding="utf-8")

for heading in (
    "## Release Images",
    "## Upgrade Runbook",
    "## Backup Runbook",
    "## Restore Runbook",
    "## Health And Smoke Checks",
    "## Operational Security Checklist",
    "## Rollback Notes",
):
    require(heading in operations, f"docs/operations.md missing {heading}")

for phrase in (
    "Back up the canonical state, not rebuildable projections alone",
    "pg_dump --format=custom",
    "pg_restore --clean --if-exists",
    "docker compose stop api worker web",
    "docker compose run --rm migrate migrate",
    "docker compose up -d api worker web",
    "make local-acceptance",
    "make docker-smoke",
    "make api-smoke",
    "make audit-export-check",
    "EXPORT=retos-audit-export.json",
    "curl --fail http://localhost:8000/versionz",
    "RETOS_VERSION",
    "RETOS_REVISION",
    "RETOS_CREATED",
    "export RETOS_IMAGE_TAG=<previous-tag>",
    "restore the backup captured",
    "backup-restore-drill-template.md",
    "target-security-review-template.md",
    "make target-security-review-check",
    "calibration-scope-decision-template.md",
    "make calibration-scope-decision-check",
):
    require(phrase in operations, f"docs/operations.md missing operational phrase: {phrase}")

for volume in (
    "retos_storage",
    "retos_eval_reports",
    "retos_eval_datasets",
    "retos_index",
):
    require(volume in operations, f"docs/operations.md missing backup volume: {volume}")

require(
    operations.count("API/worker pair.") == 1,
    "restore warning must not be duplicated",
)
require(
    "backup_dir=\"backups/" in operations,
    "backup examples must write under backups/",
)
require("backups/" in gitignore or "backups" in gitignore, ".gitignore must exclude local backups")
require(
    "backups/" in dockerignore or "backups" in dockerignore,
    ".dockerignore must exclude local backups",
)
require("/audit/export" in api_smoke, "API smoke must exercise audit export")

for phrase in (
    "Backup and restore commands were rehearsed against a disposable environment",
    "/audit/export` validates hash-chain fields",
    "make audit-export-check EXPORT=retos-audit-export.json",
    "Operator has recorded rollback steps and previous image tag",
    "Target security review is completed and linked in the promotion record",
):
    require(
        phrase in production_readiness,
        f"docs/production-readiness.md missing checklist phrase: {phrase}",
    )

for phrase in (
    "Backup artifact path",
    "Restore rehearsed in disposable environment",
    "Health checks after restore",
    "/audit/export` hash-chain snapshot reviewed",
    "Rollback command rehearsed",
    "Data restore trigger criteria",
):
    require(
        phrase in promotion_template,
        f"promotion evidence template missing operational evidence field: {phrase}",
    )

for phrase in (
    "Backup And Restore Drill Evidence Template",
    "Postgres dump path",
    "`make api-smoke` output",
    "`make audit-export-check EXPORT=retos-audit-export.json` output",
    "`/audit/export` head hash",
    "Promotion impact",
):
    require(
        phrase in drill_template,
        f"backup/restore drill template missing evidence field: {phrase}",
    )

for phrase in (
    "Target Security Review Evidence Template",
    "CORS origins reviewed",
    "API exposure reviewed",
    "Provider API keys stored in secret manager",
    "Audit hash-chain validation output",
    "Rollback owner",
    "Accepted risks",
    "Promotion impact",
):
    require(
        phrase in target_security_template,
        f"target security review template missing evidence field: {phrase}",
    )

for phrase in (
    "Calibration Scope Decision Evidence Template",
    "Pilot scope accepted",
    "Accepted scope limit",
    "Broader trend evidence attached",
    "Regression tolerance",
    "Calibration decision",
    "Promotion impact",
):
    require(
        phrase in calibration_scope_template,
        f"calibration scope decision template missing evidence field: {phrase}",
    )

print("Operations runbook OK: backup, restore, rollback, audit export, and evidence fields are aligned.")
PY
