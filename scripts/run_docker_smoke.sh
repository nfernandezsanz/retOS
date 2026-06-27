#!/usr/bin/env bash
set -euo pipefail

project="${RETOS_DOCKER_SMOKE_PROJECT:-retos_smoke}"
keep="${RETOS_DOCKER_SMOKE_KEEP:-0}"
compose=(docker compose --env-file .env.example -p "${project}")
python_bin="${PYTHON:-}"

if [[ -z "${python_bin}" ]]; then
  if [[ -x ".venv/bin/python" ]]; then
    python_bin=".venv/bin/python"
  else
    python_bin="python3"
  fi
fi

dump_diagnostics() {
  "${compose[@]}" ps -a || true
  "${compose[@]}" logs --no-color --tail 200 postgres rabbitmq migrate api worker web || true
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
"${compose[@]}" exec -T api python - <<'PY'
from pathlib import Path

import pymupdf

root = Path("/var/lib/retos/storage/smoke-corpus")
root.mkdir(parents=True, exist_ok=True)
(root / "apollo-notes.txt").write_text(
    "Apollo guidance computers used deterministic checklists.\n",
    encoding="utf-8",
)
(root / "biology.md").write_text(
    "# Biology\n\nOcean biology notes mention plankton and salinity.\n",
    encoding="utf-8",
)
document = pymupdf.open()
page = document.new_page()
page.insert_text((72, 72), "Mars rover sample caching mission brief.")
document.save(root / "mission-brief.pdf")
document.close()
PY
curl --fail --silent --show-error http://127.0.0.1:8000/healthz >/dev/null
curl --fail --silent --show-error http://127.0.0.1:8080/ >/dev/null
RETOS_BOOTSTRAP_ADMIN_PASSWORD=retos-dev-admin-change-me \
  RETOS_EXPECT_WORKER=1 \
  RETOS_SMOKE_SCAN_SOURCE_URI=file:///var/lib/retos/storage/smoke-corpus \
  "${python_bin}" backend/scripts/smoke_api.py http://127.0.0.1:8000
