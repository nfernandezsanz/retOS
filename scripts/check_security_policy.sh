#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
from __future__ import annotations

from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"Security policy failed: {message}")


paths = {
    "security": Path("SECURITY.md"),
    "readme": Path("README.md"),
    "operations": Path("docs/operations.md"),
    "production_readiness": Path("docs/production-readiness.md"),
    "target_security_review": Path("docs/releases/evidence/target-security-review-template.md"),
}

for name, path in paths.items():
    require(path.is_file() and path.stat().st_size > 0, f"missing or empty {name}: {path}")

security = paths["security"].read_text(encoding="utf-8")
readme = paths["readme"].read_text(encoding="utf-8")
operations = paths["operations"].read_text(encoding="utf-8")
production_readiness = paths["production_readiness"].read_text(encoding="utf-8")
target_security_review = paths["target_security_review"].read_text(encoding="utf-8")

for heading in (
    "## Reporting",
    "## Supported Versions",
    "## Defaults",
    "## Sensitive Data",
    "## Production Human Review",
    "## Machine Guards",
):
    require(heading in security, f"SECURITY.md missing {heading}")

for phrase in (
    "pre-alpha software",
    "GitHub Security Advisories",
    "Paid LLM calls are disabled by default",
    "Production requires a strong JWT secret",
    "development bootstrap admin password is rejected",
    "Passwords are hashed with Argon2",
    "CORS origins must be explicit",
    "Provider readiness must expose missing configuration names, never provider key values",
    "RETOS_ALLOW_PAID_LLM",
    "RETOS_JWT_SECRET",
    "provider API keys",
    "/audit/export",
    "GHCR digests",
    "SBOM/provenance",
    "Cosign signature verification",
    "shared API/worker/migrate image ID",
    "docs/releases/evidence/target-security-review-template.md",
    "make local-acceptance",
    "make target-security-review-check",
    "make dependency-audit",
    "make production-preflight",
    "make ci-status-check",
):
    require(phrase in security, f"SECURITY.md missing security phrase: {phrase}")

for doc_name, content in (
    ("README.md", readme),
    ("docs/operations.md", operations),
    ("docs/production-readiness.md", production_readiness),
):
    require("SECURITY.md" in content, f"{doc_name} must link SECURITY.md")

for phrase in (
    "Target Security Review Evidence Template",
    "Auth And Access",
    "Secrets And Provider Keys",
    "Network And Runtime Exposure",
    "Data Handling And Audit",
    "Release Provenance",
    "Operations And Rollback",
):
    require(
        phrase in target_security_review,
        f"target security review template missing security phrase: {phrase}",
    )

print("Security policy OK: reporting, defaults, human review, and machine guards are aligned.")
PY
