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
import json
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

dataset_root = Path("/var/lib/retos/evals/datasets")
dataset_root.mkdir(parents=True, exist_ok=True)
(dataset_root / "smoke-squad.json").write_text(
    json.dumps(
        {
            "version": "v2.0",
            "data": [
                {
                    "title": "Solar System",
                    "paragraphs": [
                        {
                            "context": (
                                "Mars is called the Red Planet because iron oxide dust "
                                "covers much of its surface."
                            ),
                            "qas": [
                                {
                                    "id": "mars-red-planet",
                                    "question": "Why is Mars called the Red Planet?",
                                    "answers": [
                                        {"text": "iron oxide dust", "answer_start": 39}
                                    ],
                                    "is_impossible": False,
                                },
                                {
                                    "id": "mars-ocean-depth",
                                    "question": "How deep are the oceans on Mars today?",
                                    "answers": [],
                                    "is_impossible": True,
                                },
                            ],
                        }
                    ],
                }
            ],
        }
    ),
    encoding="utf-8",
)
(dataset_root / "smoke-hotpotqa.json").write_text(
    json.dumps(
        [
            {
                "_id": "vela-air-force",
                "question": (
                    "Which agency operated Vela spacecraft in the United States "
                    "Air Force history?"
                ),
                "answer": "United States Air Force",
                "supporting_facts": [["Vela", 0], ["United States Air Force", 0]],
                "context": [
                    [
                        "Vela",
                        ["Vela spacecraft were satellites operated by the United States Air Force."],
                    ],
                    [
                        "United States Air Force",
                        ["The United States Air Force operated satellite programs."],
                    ],
                ],
            }
        ]
    ),
    encoding="utf-8",
)
PY
curl --fail --silent --show-error http://127.0.0.1:8000/healthz >/dev/null
curl --fail --silent --show-error http://127.0.0.1:8080/ >/dev/null
RETOS_BOOTSTRAP_ADMIN_PASSWORD=retos-dev-admin-change-me \
  RETOS_EXPECT_WORKER=1 \
  RETOS_EVAL_DATASET_ROOT=/var/lib/retos/evals/datasets \
  RETOS_EVAL_REPORT_ROOT=/var/lib/retos/evals/reports \
  RETOS_SMOKE_PREPARE_DATASETS=0 \
  RETOS_SMOKE_CHECK_REPORT_FILES=0 \
  RETOS_SMOKE_SCAN_SOURCE_URI=file:///var/lib/retos/storage/smoke-corpus \
  "${python_bin}" backend/scripts/smoke_api.py http://127.0.0.1:8000
"${compose[@]}" exec -T api test -f /var/lib/retos/evals/reports/api-smoke-squad.json
"${compose[@]}" exec -T api test -f /var/lib/retos/evals/reports/api-smoke-squad.md
"${compose[@]}" exec -T api test -f /var/lib/retos/evals/reports/api-smoke-hotpotqa.json
"${compose[@]}" exec -T api test -f /var/lib/retos/evals/reports/api-smoke-hotpotqa.md
