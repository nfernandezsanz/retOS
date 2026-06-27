#!/usr/bin/env bash
set -euo pipefail

host="${RETOS_SMOKE_HOST:-127.0.0.1}"
port="${RETOS_SMOKE_PORT:-8000}"
base_url="${RETOS_SMOKE_BASE_URL:-http://${host}:${port}}"
log_file="${TMPDIR:-/tmp}/retos-api-smoke.log"
db_file="${TMPDIR:-/tmp}/retos-api-smoke-$RANDOM.db"
index_dir="${TMPDIR:-/tmp}/retos-api-smoke-index-$RANDOM"
storage_dir="${TMPDIR:-/tmp}/retos-api-smoke-storage-$RANDOM"
eval_dataset_dir="${TMPDIR:-/tmp}/retos-api-smoke-eval-datasets-$RANDOM"
eval_report_dir="${TMPDIR:-/tmp}/retos-api-smoke-eval-reports-$RANDOM"
python_bin="${PYTHON:-python}"

if [[ -z "${PYTHON:-}" && -x "../.venv/bin/python" ]]; then
  python_bin="../.venv/bin/python"
fi

export PYTHONPATH="${PYTHONPATH:-src}"
export RETOS_ENV="${RETOS_ENV:-test}"
export RETOS_ALLOW_PAID_LLM="${RETOS_ALLOW_PAID_LLM:-false}"
export RETOS_JWT_SECRET="${RETOS_JWT_SECRET:-test-secret-value-that-is-long-enough}"
export RETOS_BOOTSTRAP_ADMIN_EMAIL="${RETOS_BOOTSTRAP_ADMIN_EMAIL:-admin@retos.dev}"
export RETOS_BOOTSTRAP_ADMIN_PASSWORD="${RETOS_BOOTSTRAP_ADMIN_PASSWORD:-test-admin-password}"
export RETOS_DATABASE_URL="${RETOS_DATABASE_URL:-sqlite+aiosqlite:///${db_file}}"
export RETOS_DATABASE_CREATE_ALL="${RETOS_DATABASE_CREATE_ALL:-true}"
export RETOS_INDEX_ROOT="${RETOS_INDEX_ROOT:-${index_dir}}"
export RETOS_STORAGE_ROOT="${RETOS_STORAGE_ROOT:-${storage_dir}}"
export RETOS_EVAL_DATASET_ROOT="${RETOS_EVAL_DATASET_ROOT:-${eval_dataset_dir}}"
export RETOS_EVAL_REPORT_ROOT="${RETOS_EVAL_REPORT_ROOT:-${eval_report_dir}}"

"${python_bin}" -m uvicorn retos.main:app --host "${host}" --port "${port}" >"${log_file}" 2>&1 &
server_pid="$!"

cleanup() {
  kill "${server_pid}" >/dev/null 2>&1 || true
  wait "${server_pid}" >/dev/null 2>&1 || true
  rm -f "${db_file}"
  rm -rf "${index_dir}" "${storage_dir}" "${eval_dataset_dir}" "${eval_report_dir}"
}
trap cleanup EXIT

"${python_bin}" scripts/wait_http.py "${base_url}/healthz" 30
"${python_bin}" scripts/smoke_api.py "${base_url}"
