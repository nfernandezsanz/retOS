#!/usr/bin/env bash
set -euo pipefail

python_bin="${BACKEND_PYTHON:-python3}"

"${python_bin}" -m pip_audit -r backend/requirements.txt

(
  cd frontend
  npm audit --audit-level=high
)
