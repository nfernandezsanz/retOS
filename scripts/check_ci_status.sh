#!/usr/bin/env bash
set -euo pipefail

repo="${RETOS_GITHUB_REPOSITORY:-nfernandezsanz/retOS}"
sha="${RETOS_CI_SHA:-$(git rev-parse HEAD)}"
api_root="${GITHUB_API_URL:-https://api.github.com}"
auth_args=()

if [[ -n "${GITHUB_TOKEN:-}" ]]; then
  auth_args=(-H "Authorization: Bearer ${GITHUB_TOKEN}")
fi

tmp_run="$(mktemp)"
tmp_jobs="$(mktemp)"
trap 'rm -f "${tmp_run}" "${tmp_jobs}"' EXIT

curl -fsSL "${auth_args[@]+"${auth_args[@]}"}" \
  -H "Accept: application/vnd.github+json" \
  "${api_root}/repos/${repo}/actions/runs?head_sha=${sha}&per_page=10" \
  -o "${tmp_run}"

python3 - "${tmp_run}" "${tmp_jobs}" "${api_root}" "${repo}" "${sha}" "${auth_args[@]+"${auth_args[@]}"}" <<'PY'
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def fail(message: str) -> None:
    raise SystemExit(f"CI status failed: {message}")


run_path = Path(sys.argv[1])
jobs_path = Path(sys.argv[2])
api_root = sys.argv[3].rstrip("/")
repo = sys.argv[4]
sha = sys.argv[5]
auth_args = sys.argv[6:]

runs = json.loads(run_path.read_text(encoding="utf-8")).get("workflow_runs", [])
matching = [run for run in runs if run.get("head_sha") == sha and run.get("name") == "CI"]
if not matching:
    fail(f"no CI workflow run found for {repo}@{sha[:7]}")

run = sorted(matching, key=lambda item: item.get("created_at", ""), reverse=True)[0]
status = run.get("status")
conclusion = run.get("conclusion")
if status != "completed" or conclusion != "success":
    fail(
        f"CI run {run.get('id')} for {sha[:7]} is {status}/{conclusion}; "
        f"see {run.get('html_url')}"
    )

jobs_url = f"{api_root}/repos/{repo}/actions/runs/{run['id']}/jobs?per_page=50"
curl_cmd = [
    "curl",
    "-fsSL",
    *auth_args,
    "-H",
    "Accept: application/vnd.github+json",
    jobs_url,
    "-o",
    str(jobs_path),
]
subprocess.run(curl_cmd, check=True)
jobs = json.loads(jobs_path.read_text(encoding="utf-8")).get("jobs", [])
required_jobs = {"backend", "frontend", "docker"}
seen = {job.get("name"): job for job in jobs}
missing = sorted(required_jobs - set(seen))
if missing:
    fail(f"CI run {run['id']} is missing required job(s): {', '.join(missing)}")

failed = [
    f"{name}={seen[name].get('status')}/{seen[name].get('conclusion')}"
    for name in sorted(required_jobs)
    if seen[name].get("status") != "completed" or seen[name].get("conclusion") != "success"
]
if failed:
    fail(f"required CI job(s) are not successful: {', '.join(failed)}")

print(
    "CI status OK: "
    f"{repo}@{sha[:7]} run {run['id']} completed success "
    f"with backend, frontend, and docker jobs. {run.get('html_url')}"
)
PY
