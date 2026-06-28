#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
from __future__ import annotations

from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"Release workflow failed: {message}")


workflow_path = Path(".github/workflows/release.yml")
docker_docs_path = Path("docs/docker.md")
operations_path = Path("docs/operations.md")
release_process_path = Path("docs/release-process.md")

for path in (workflow_path, docker_docs_path, operations_path, release_process_path):
    require(path.is_file() and path.stat().st_size > 0, f"missing or empty {path}")

workflow = workflow_path.read_text(encoding="utf-8")
docker_docs = docker_docs_path.read_text(encoding="utf-8")
operations = operations_path.read_text(encoding="utf-8")
release_process = release_process_path.read_text(encoding="utf-8")

required_workflow_phrases = (
    "name: Release Images",
    "packages: write",
    "id-token: write",
    "attestations: write",
    "ghcr.io",
    "retos-backend",
    "retos-web",
    "backend/Dockerfile",
    "target: backend-runtime",
    "frontend/Dockerfile",
    "docker/build-push-action@v6",
    "sbom: true",
    "provenance: mode=max",
    "sigstore/cosign-installer@v4",
    "cosign sign --yes",
    "Verify published image signatures",
    "cosign verify",
    "--certificate-identity-regexp",
    "--certificate-oidc-issuer",
    "needs:",
    "python-version: \"3.14\"",
    "node-version: \"24\"",
    "black --check --diff",
    "ruff check",
    "mypy src",
    "pytest",
    "npm run check",
    "make release-check",
    "make production-preflight",
)

for phrase in required_workflow_phrases:
    require(phrase in workflow, f"release.yml missing {phrase}")

require(
    "worker" not in workflow.lower() or "retos-worker" not in workflow.lower(),
    "release workflow must not publish a separate worker image",
)

for phrase in (
    ".github/workflows/release.yml",
    "GHCR",
    "Cosign",
    "signature verification",
    "SBOM",
    "provenance",
    "retos-backend",
    "retos-web",
):
    require(phrase in docker_docs, f"docs/docker.md missing release publishing phrase: {phrase}")
    require(phrase in operations, f"docs/operations.md missing release publishing phrase: {phrase}")
    require(phrase in release_process, f"docs/release-process.md missing release publishing phrase: {phrase}")

print("Release workflow OK: GHCR publishing, SBOM/provenance, signing, and signature verification are documented.")
PY
