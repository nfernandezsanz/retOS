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
  "LICENSE"
  "CHANGELOG.md"
  ".env.example"
  "docker-compose.yml"
  "docs/release-process.md"
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
scripts/check_release_notes.sh >/dev/null

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
    "docs/release-process.md",
    "docker compose --env-file .env.example config",
    "make docker-smoke",
):
    require(phrase in operations, f"docs/operations.md missing operational phrase: {phrase}")

require(
    "one shared backend image reused by API, worker, and migrations" in readme,
    "README must document the shared backend image topology",
)
require(
    "API, worker, and migrate share the same `retos-backend` image" in docker_docs,
    "docs/docker.md must document the shared backend runtime",
)
require(
    "docs/operations.md" in readme,
    "README must link the operations guide",
)
require(
    "CHANGELOG.md" in readme,
    "README must link the changelog",
)

print("Release readiness OK: docs, defaults, and Docker topology are aligned.")
PY
