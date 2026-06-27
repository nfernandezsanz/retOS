#!/usr/bin/env bash
set -euo pipefail

project="${RETOS_DOCKER_SMOKE_PROJECT:-retos_smoke}"
keep="${RETOS_DOCKER_SMOKE_KEEP:-0}"
compose=(docker compose --env-file .env.example -p "${project}")

dump_diagnostics() {
  "${compose[@]}" ps -a || true
  "${compose[@]}" logs --no-color --tail 200 postgres rabbitmq api worker web || true
}

cleanup() {
  if [[ "${keep}" != "1" ]]; then
    "${compose[@]}" down --volumes --remove-orphans >/dev/null 2>&1 || true
  fi
}

finish() {
  status=$?
  if [[ "${status}" -ne 0 ]]; then
    dump_diagnostics
  fi
  cleanup
  exit "${status}"
}

trap finish EXIT

"${compose[@]}" down --volumes --remove-orphans >/dev/null 2>&1 || true
"${compose[@]}" up --build -d --wait --wait-timeout 180 postgres rabbitmq api worker web
curl --fail --silent --show-error http://127.0.0.1:8000/healthz >/dev/null
curl --fail --silent --show-error http://127.0.0.1:8080/ >/dev/null
