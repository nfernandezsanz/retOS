#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
from __future__ import annotations

from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"CI workflow failed: {message}")


workflow_path = Path(".github/workflows/ci.yml")
readme_path = Path("README.md")
production_path = Path("docs/production-readiness.md")

for path in (workflow_path, readme_path, production_path):
    require(path.is_file() and path.stat().st_size > 0, f"missing or empty {path}")

workflow = workflow_path.read_text(encoding="utf-8")
readme = readme_path.read_text(encoding="utf-8")
production = production_path.read_text(encoding="utf-8")

required_workflow_phrases = (
    "name: CI",
    "pull_request:",
    "branches:",
    "- main",
    "schedule:",
    "workflow_dispatch:",
    "backend:",
    "frontend:",
    "docker:",
    "audit-evidence:",
    "needs:",
    "- backend",
    "- frontend",
    "- docker",
    "actions/checkout@v6",
    "actions/setup-python@v6",
    "python-version: \"3.14\"",
    "actions/setup-node@v6",
    "node-version: \"24\"",
    "python -m pip install -r backend/requirements-dev.txt",
    "black --check --diff src tests scripts",
    "black --check --diff scripts",
    "ruff check src tests scripts",
    "ruff check scripts",
    "mypy src",
    "python -m pip_audit -r backend/requirements.txt",
    "pytest",
    "python scripts/check_branch_coverage.py --fail-under 90.65",
    "retos-backend-coverage-${{ github.sha }}",
    "backend/coverage.json",
    "PYTHONPATH=src python scripts/run_eval_smoke.py --format markdown",
    "scripts/run_api_smoke.sh",
    "npm ci",
    "npm audit --audit-level=high",
    "npm run format:check",
    "npm run check",
    "npx playwright install --with-deps chromium",
    "npm run e2e",
    "npm run visual-audit",
    "retos-visual-audit-${{ github.sha }}",
    "frontend/visual-audit/*.png",
    "frontend/visual-audit/manifest.json",
    "docker compose --env-file .env.example config",
    "scripts/check_docker_topology.sh",
    "scripts/check_release_readiness.sh",
    "scripts/check_audit_pack.sh",
    "scripts/check_production_preflight.sh",
    "scripts/check_auditor_evidence_matrix.sh",
    "scripts/check_branding_assets.sh",
    "scripts/check_release_workflow.sh",
    "scripts/check_release_notes.sh",
    "scripts/check_versioned_release_notes.sh",
    "scripts/check_image_metadata.sh",
    "make auditor-static-check",
    "scripts/run_docker_smoke.sh",
    "actions/download-artifact@v4",
    "retos-audit-manifest-${{ github.sha }}",
    "retos-audit-handoff-${{ github.sha }}",
    "make audit-manifest OUTPUT=retos-audit-manifest.json",
    "make audit-handoff-report MANIFEST=retos-audit-manifest.json OUTPUT=retos-audit-handoff.md",
    "if-no-files-found: error",
)

for phrase in required_workflow_phrases:
    require(phrase in workflow, f"ci.yml missing {phrase}")

for phrase in (
    "actions/workflows/ci.yml/badge.svg?branch=main",
    "backend/root Python format/PEP 8",
    "frontend Prettier format",
    "make ci-status-check",
):
    require(phrase in readme, f"README.md missing CI phrase: {phrase}")

for phrase in (
    "CI health",
    "make ci-status-check",
    "root Python audit/release scripts",
    "Current HEAD CI",
):
    require(phrase in production, f"production readiness missing CI phrase: {phrase}")

print("CI workflow OK: jobs, local gates, artifacts, and audit handoff are aligned.")
PY
