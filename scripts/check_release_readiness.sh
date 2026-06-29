#!/usr/bin/env bash
set -euo pipefail

required_files=(
  "README.md"
  "docs/docker.md"
  "docs/operations.md"
  "docs/api-integration.md"
  "docs/evals.md"
  "docs/database.md"
  "CONTRIBUTING.md"
  "SECURITY.md"
  "LICENSE"
  "CHANGELOG.md"
  "Makefile"
  "docs/releases/README.md"
  "docs/releases/2026.06.28-alpha.1.md"
  "docs/releases/evidence/calibration-scope-decision-template.md"
  "docs/releases/evidence/backup-restore-drill-template.md"
  "docs/releases/evidence/production-promotion-template.md"
  "docs/releases/evidence/target-security-review-template.md"
  ".env.example"
  "docker-compose.yml"
  ".gitignore"
  ".dockerignore"
  "docs/release-process.md"
  "docs/production-readiness.md"
  "scripts/check_production_preflight.sh"
  "scripts/check_published_release_evidence.sh"
  "scripts/check_env_security.py"
  "scripts/check_backup_restore_drill.py"
  "scripts/check_promotion_template.py"
  "scripts/check_target_security_review.py"
  "scripts/check_calibration_scope_decision.py"
  "scripts/check_eval_calibration_evidence.py"
  "scripts/check_eval_calibration_trend.py"
  "scripts/check_visual_audit.py"
  "scripts/export_audit_manifest.py"
  "scripts/check_audit_manifest.py"
  "scripts/export_audit_bundle.py"
  "scripts/check_audit_bundle.py"
)

for file in "${required_files[@]}"; do
  if [[ ! -s "${file}" ]]; then
    echo "Release readiness failed: missing or empty ${file}" >&2
    exit 1
  fi
done

scripts/check_docker_topology.sh >/dev/null
scripts/check_image_metadata.sh >/dev/null
scripts/check_image_size.sh >/dev/null
scripts/check_release_workflow.sh >/dev/null
scripts/check_release_notes.sh >/dev/null
scripts/check_versioned_release_notes.sh >/dev/null
python3 scripts/check_env_security.py >/dev/null
python3 scripts/check_backup_restore_drill.py >/dev/null
python3 scripts/check_promotion_template.py >/dev/null
python3 scripts/check_target_security_review.py >/dev/null
python3 scripts/check_calibration_scope_decision.py >/dev/null
python3 scripts/check_eval_calibration_evidence.py >/dev/null
python3 scripts/check_eval_calibration_trend.py >/dev/null
python3 scripts/check_visual_audit.py >/dev/null
scripts/check_audit_pack.sh >/dev/null
scripts/check_branding_assets.sh >/dev/null
scripts/check_security_policy.sh >/dev/null
scripts/check_ignore_hygiene.sh >/dev/null
scripts/check_operations_runbook.sh >/dev/null
RETOS_RELEASE_EVIDENCE_DRY_RUN=1 \
  VERSION=2026.06.28-alpha.1 \
  BACKEND_DIGEST=sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa \
  WEB_DIGEST=sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb \
  scripts/check_published_release_evidence.sh >/dev/null

python3 - <<'PY'
from __future__ import annotations

from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"Release readiness failed: {message}")


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


env = parse_env(Path(".env.example"))
operations = Path("docs/operations.md").read_text(encoding="utf-8")
docker_docs = Path("docs/docker.md").read_text(encoding="utf-8")
readme = Path("README.md").read_text(encoding="utf-8")
audit_pack = Path("docs/production-readiness.md").read_text(encoding="utf-8")
contributing = Path("CONTRIBUTING.md").read_text(encoding="utf-8")
makefile = Path("Makefile").read_text(encoding="utf-8")

require(env.get("RETOS_ALLOW_PAID_LLM") == "false", "paid LLMs must be disabled by default")
require(env.get("RETOS_PROVIDER") == "local", "local provider must be the default")
require(env.get("RETOS_AGENT_RUNTIME") == "deterministic", "deterministic agent runtime must be the default")
require(env.get("RETOS_OLLAMA_MODEL") == "gemma4", "Gemma 4 must be the default Ollama model")
require(
    env.get("RETOS_JWT_SECRET") == "change-this-development-secret-at-least-32-chars",
    "example JWT secret must stay an obvious development placeholder",
)
require(
    env.get("RETOS_BOOTSTRAP_ADMIN_PASSWORD") == "retos-dev-admin-change-me",
    "example admin password must stay an obvious development placeholder",
)

for heading in (
    "## Release Images",
    "## Upgrade Runbook",
    "## Backup Runbook",
    "## Restore Runbook",
    "## Health And Smoke Checks",
    "## Operational Security Checklist",
):
    require(heading in operations, f"docs/operations.md missing {heading}")

for phrase in (
    "retos-backend",
    "retos-web",
    "RETOS_IMAGE_TAG",
    "org.opencontainers.image",
    "RETOS_BACKEND_IMAGE_MAX_BYTES",
    "RETOS_WEB_IMAGE_MAX_BYTES",
    ".github/workflows/release.yml",
    "GHCR",
    "Cosign",
    "SBOM",
    "provenance",
    "docs/release-process.md",
    "docker compose --env-file .env.example config",
    "make doctor",
    "make docker-runtime-image-check",
    "make local-acceptance",
    "make docker-smoke",
    "make release-evidence-check",
    "tag-to-digest resolution",
):
    require(phrase in operations, f"docs/operations.md missing operational phrase: {phrase}")

published_evidence = Path("scripts/check_published_release_evidence.sh").read_text(encoding="utf-8")
for phrase in (
    "validate_version",
    "docker buildx imagetools inspect",
    "RETOS_SKIP_TAG_DIGEST_CHECK",
    "Immutable tags resolve to the recorded digests",
):
    require(phrase in published_evidence, f"published release evidence checker missing {phrase}")

require(
    "one shared backend image reused by API, worker, and migrations" in readme,
    "README must document the shared backend image topology",
)
require(
    "API, worker, and migrate share the same `retos-backend` image" in docker_docs,
    "docs/docker.md must document the shared backend runtime",
)
require(
    "scripts/check_backend_runtime_image.sh" in docker_docs,
    "docs/docker.md must document the backend runtime image ID guard",
)
require(
    "docs/operations.md" in readme,
    "README must link the operations guide",
)
require(
    "CHANGELOG.md" in readme,
    "README must link the changelog",
)
require(
    "docs/production-readiness.md" in readme,
    "README must link the production readiness audit pack",
)
require(
    "make doctor" in readme and "make doctor" in docker_docs and "make doctor" in audit_pack,
    "README, Docker docs, and production readiness pack must expose the local doctor",
)
require(
    "make env-security-check" in readme
    and "make env-security-check" in docker_docs
    and "make env-security-check" in audit_pack,
    "README, Docker docs, and production readiness pack must expose env-security-check",
)
require(
    "make promotion-template-check" in readme
    and "make promotion-template-check" in audit_pack,
    "README and production readiness pack must expose promotion-template-check",
)
require(
    "make target-security-review-check" in readme
    and "make target-security-review-check" in audit_pack,
    "README and production readiness pack must expose target-security-review-check",
)
require(
    "make calibration-scope-decision-check" in readme
    and "make calibration-scope-decision-check" in audit_pack,
    "README and production readiness pack must expose calibration-scope-decision-check",
)
require(
    "make backup-restore-drill-check" in readme
    and "make backup-restore-drill-check" in audit_pack,
    "README and production readiness pack must expose backup-restore-drill-check",
)
require(
    "make docker-seed-demo" in readme and "make docker-seed-demo" in docker_docs,
    "README and Docker docs must expose the local Docker demo seed",
)
require(
    "seed-demo:" in makefile and "docker-seed-demo:" in makefile,
    "Makefile must expose local and Docker demo seed targets",
)
require(
    "make local-acceptance" in contributing,
    "CONTRIBUTING.md must document the local acceptance gate",
)
local_acceptance_line = next(
    (line for line in makefile.splitlines() if line.startswith("local-acceptance:")),
    "",
)
require(local_acceptance_line, "Makefile must define local-acceptance")
for dependency in (
    "doctor",
    "check",
    "integration",
    "frontend-test",
    "frontend-visual-audit",
    "docker-config",
    "auditor-handoff-check",
    "docker-smoke",
):
    require(
        dependency in local_acceptance_line,
        f"local-acceptance must depend on {dependency}",
    )
require(
    "make local-acceptance Run the local pre-audit acceptance gate" in makefile,
    "Makefile help must expose local-acceptance",
)
require(
    "make env-security-check Validate active .env security posture" in makefile,
    "Makefile help must expose env-security-check",
)
require(
    "make visual-audit-check Validate local visual-audit manifest and screenshot hashes"
    in makefile,
    "Makefile help must expose visual-audit-check",
)
require(
    "RetOS is not production-promoted yet" in audit_pack,
    "production readiness pack must avoid overclaiming production promotion",
)
require(
    "Promotion Blockers" in audit_pack,
    "production readiness pack must list promotion blockers",
)

print("Release readiness OK: docs, defaults, and Docker topology are aligned.")
PY
