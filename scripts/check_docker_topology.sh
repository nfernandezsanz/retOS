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

builds = {role: services[role].get("build") for role in backend_roles}
missing_builds = [role for role, build in builds.items() if not build]
if missing_builds:
    raise SystemExit(
        "Every backend role must declare the shared backend build so each role "
        f"can be built directly. Missing build on: {', '.join(missing_builds)}"
    )

expected_context = str(Path.cwd())
for role, build in builds.items():
    actual_context = str(Path(build.get("context", "")).resolve())
    if actual_context != expected_context:
        raise SystemExit(
            f"The {role} backend build must use the repository root as context: "
            f"expected {expected_context}, got {actual_context}"
        )

    if build.get("dockerfile") != "backend/Dockerfile":
        raise SystemExit(
            f"The {role} backend build must use backend/Dockerfile, got "
            f"{build.get('dockerfile')}"
        )

    if build.get("target") != "backend-runtime":
        raise SystemExit(
            f"The {role} backend build must target backend-runtime, got "
            f"{build.get('target')}"
        )

reference_build = {
    key: builds["api"].get(key)
    for key in ("context", "dockerfile", "target")
}
for role in ("worker", "migrate"):
    candidate = {
        key: builds[role].get(key)
        for key in ("context", "dockerfile", "target")
    }
    if candidate != reference_build:
        raise SystemExit(
            "Backend roles must share the same build definition. "
            f"api={reference_build}, {role}={candidate}"
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
