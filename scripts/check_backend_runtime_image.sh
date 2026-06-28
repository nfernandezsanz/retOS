#!/usr/bin/env bash
set -euo pipefail

project="${RETOS_DOCKER_PROJECT:-retos}"
compose=(docker compose -p "${project}")

if [[ "${RETOS_DOCKER_USE_ENV_FILE:-1}" == "1" ]]; then
  compose=(docker compose --env-file "${RETOS_COMPOSE_ENV_FILE:-.env.example}" -p "${project}")
fi

image_id_for_role() {
  role="$1"
  container_id="$("${compose[@]}" ps -aq "${role}")"
  if [[ -z "${container_id}" ]]; then
    raise_message="Missing container for backend role '${role}'. Start the stack before running this check."
    echo "${raise_message}" >&2
    exit 1
  fi
  docker inspect --format '{{.Image}}' "${container_id}"
}

api_image_id="$(image_id_for_role api)"
worker_image_id="$(image_id_for_role worker)"
migrate_image_id="$(image_id_for_role migrate)"

if [[ "${api_image_id}" != "${worker_image_id}" || "${api_image_id}" != "${migrate_image_id}" ]]; then
  echo "Backend roles must run the exact same image ID." >&2
  echo "  api: ${api_image_id}" >&2
  echo "  worker: ${worker_image_id}" >&2
  echo "  migrate: ${migrate_image_id}" >&2
  exit 1
fi

echo "Backend runtime image OK: api, worker, and migrate run ${api_image_id}."
