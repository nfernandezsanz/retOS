#!/usr/bin/env bash
set -euo pipefail

compose_file="${RETOS_COMPOSE_FILE:-docker-compose.yml}"
env_file="${RETOS_COMPOSE_ENV_FILE:-.env.example}"
config_file="$(mktemp)"

cleanup() {
  rm -f "${config_file}"
}

trap cleanup EXIT

docker compose --file "${compose_file}" --env-file "${env_file}" config --format json >"${config_file}"

python3 - "${config_file}" <<'PY'
import json
import sys
from pathlib import Path

with open(sys.argv[1], encoding="utf-8") as handle:
    config = json.load(handle)
services = config["services"]
backend_roles = ("api", "worker", "migrate")

missing = [role for role in backend_roles if role not in services]
if missing:
    raise SystemExit(f"Missing backend service(s): {', '.join(missing)}")

images = {role: services[role].get("image") for role in backend_roles}
if len(set(images.values())) != 1:
    details = ", ".join(f"{role}={image}" for role, image in images.items())
    raise SystemExit(f"Backend roles must share one image: {details}")

unexpected_builds = [
    role for role in ("worker", "migrate") if "build" in services[role]
]
if unexpected_builds:
    raise SystemExit(
        "Only the api service may define the shared backend build. "
        f"Unexpected build on: {', '.join(unexpected_builds)}"
    )

api_build = services["api"].get("build")
if not api_build:
    raise SystemExit("The api service must define the shared backend image build.")

expected_context = str(Path.cwd())
actual_context = str(Path(api_build.get("context", "")).resolve())
if actual_context != expected_context:
    raise SystemExit(
        "The shared backend build must use the repository root as context: "
        f"expected {expected_context}, got {actual_context}"
    )

if api_build.get("dockerfile") != "backend/Dockerfile":
    raise SystemExit(
        "The shared backend build must use backend/Dockerfile, got "
        f"{api_build.get('dockerfile')}"
    )

if api_build.get("target") != "backend-runtime":
    raise SystemExit(
        "The shared backend build must target backend-runtime, got "
        f"{api_build.get('target')}"
    )

commands = {role: services[role].get("command") for role in backend_roles}
expected_commands = {
    "api": ["api"],
    "worker": ["worker"],
    "migrate": ["migrate"],
}
if commands != expected_commands:
    details = ", ".join(f"{role}={command}" for role, command in commands.items())
    raise SystemExit(f"Backend role commands changed unexpectedly: {details}")

print(
    "Docker topology OK: api, worker, and migrate share "
    f"{images['api']} from backend/Dockerfile target backend-runtime "
    "with role-specific commands."
)
PY
