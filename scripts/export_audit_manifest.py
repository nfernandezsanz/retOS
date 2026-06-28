#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPO = "nfernandezsanz/retOS"

CRITICAL_FILES = (
    "README.md",
    "SECURITY.md",
    "CHANGELOG.md",
    "Makefile",
    ".github/workflows/ci.yml",
    ".github/workflows/release.yml",
    "docker-compose.yml",
    "backend/Dockerfile",
    "frontend/Dockerfile",
    "docs/production-readiness.md",
    "docs/release-process.md",
    "docs/operations.md",
    "docs/docker.md",
    "docs/branding.md",
    "docs/releases/2026.06.28-alpha.1.md",
    "docs/releases/evidence/production-promotion-template.md",
    "scripts/check_ci_status.sh",
    "scripts/check_audit_pack.sh",
    "scripts/check_production_preflight.sh",
    "scripts/check_release_workflow.sh",
    "scripts/check_published_release_evidence.sh",
)

LOCAL_GATES = (
    "make check",
    "make integration",
    "make frontend-test",
    "make frontend-e2e",
    "make frontend-visual-audit",
    "docker compose --env-file .env.example config",
    "docker compose --dry-run build",
    "make docker-smoke",
    "make release-check",
    "make production-preflight",
    "make auditor-static-check",
    "make dependency-audit",
    "make security-policy-check",
    "make ignore-hygiene-check",
    "make operations-runbook-check",
    "make release-workflow-check",
    "make release-notes-check",
    "make versioned-release-notes-check",
    "make ci-status-check",
)

EXTERNAL_PROMOTION_EVIDENCE = (
    "GHCR backend and web digests from the immutable release workflow run",
    "SBOM/provenance attestations from GitHub Actions",
    "Cosign verification against published backend and web digests",
    "Accepted calibration scope or broader public-slice trend evidence",
    "Human target-environment security review",
)


def run(command: list[str]) -> str:
    return subprocess.check_output(command, cwd=ROOT, text=True).strip()


def run_optional(command: list[str]) -> str | None:
    try:
        return run(command)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(relative_path: str) -> dict[str, Any]:
    path = ROOT / relative_path
    if not path.is_file():
        return {"exists": False, "path": relative_path}
    return {
        "exists": True,
        "path": relative_path,
        "sha256": sha256(path),
        "size_bytes": path.stat().st_size,
    }


def github_ci(repo: str, sha: str) -> dict[str, Any]:
    api_root = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    headers = [
        "-H",
        "Accept: application/vnd.github+json",
        "-H",
        "User-Agent: retos-audit-manifest",
    ]
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers.extend(["-H", f"Authorization: Bearer {token}"])

    def fetch_json(url: str) -> dict[str, Any]:
        payload = subprocess.check_output(
            ["curl", "-fsSL", *headers, url], cwd=ROOT, text=True
        )
        return json.loads(payload)

    try:
        runs = fetch_json(
            f"{api_root}/repos/{repo}/actions/runs?head_sha={sha}&per_page=10"
        )
        matching = [
            run
            for run in runs.get("workflow_runs", [])
            if run.get("head_sha") == sha and run.get("name") == "CI"
        ]
        if not matching:
            return {
                "available": False,
                "reason": "no CI workflow run found for current SHA",
            }
        run_data = sorted(
            matching, key=lambda item: item.get("created_at", ""), reverse=True
        )[0]
        jobs = fetch_json(
            f"{api_root}/repos/{repo}/actions/runs/{run_data['id']}/jobs?per_page=50"
        )
    except (
        FileNotFoundError,
        subprocess.CalledProcessError,
        KeyError,
        json.JSONDecodeError,
    ) as exc:
        return {"available": False, "reason": str(exc)}

    return {
        "available": True,
        "conclusion": run_data.get("conclusion"),
        "jobs": [
            {
                "conclusion": job.get("conclusion"),
                "name": job.get("name"),
                "status": job.get("status"),
                "url": job.get("html_url"),
            }
            for job in jobs.get("jobs", [])
        ],
        "run_id": run_data.get("id"),
        "status": run_data.get("status"),
        "url": run_data.get("html_url"),
    }


def build_manifest(args: argparse.Namespace) -> dict[str, Any]:
    sha = run(["git", "rev-parse", "HEAD"])
    dirty_files = run_optional(["git", "status", "--short"]) or ""
    return {
        "ci": github_ci(args.repository, sha),
        "coverage_targets": {
            "branch_minimum_percent": 90.44,
            "last_recorded_branch_percent": 90.44,
            "last_recorded_total_percent": 95.20,
            "total_minimum_percent": 90.0,
        },
        "critical_file_hashes": [file_record(path) for path in CRITICAL_FILES],
        "external_promotion_evidence_required": list(EXTERNAL_PROMOTION_EVIDENCE),
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "local_gates_required": list(LOCAL_GATES),
        "production_promotion_ready": False,
        "production_promotion_ready_reason": (
            "Local gates and CI can be verified from this manifest, but final production "
            "promotion still requires immutable release publishing evidence and human "
            "target-environment review."
        ),
        "repository": {
            "branch": run_optional(["git", "branch", "--show-current"]),
            "commit_sha": sha,
            "commit_short_sha": run(["git", "rev-parse", "--short", "HEAD"]),
            "dirty": bool(dirty_files.strip()),
            "dirty_files": dirty_files.splitlines(),
            "remote": run_optional(["git", "config", "--get", "remote.origin.url"]),
        },
        "schema_version": 1,
        "visual_audit": {
            "ci_artifact": f"retos-visual-audit-{sha}",
            "local_screenshots": [
                file_record("frontend/visual-audit/retos-console-desktop.png"),
                file_record("frontend/visual-audit/retos-console-mobile.png"),
            ],
            "release_artifact": f"retos-release-visual-audit-{sha}",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export a RetOS local audit manifest as JSON."
    )
    parser.add_argument(
        "--repository",
        default=os.environ.get("RETOS_GITHUB_REPOSITORY", DEFAULT_REPO),
        help="GitHub repository used for CI lookup, for example owner/name.",
    )
    parser.add_argument("--output", type=Path, help="Write the manifest to this path.")
    args = parser.parse_args()

    payload = json.dumps(build_manifest(args), indent=2, sort_keys=True) + "\n"
    if args.output:
        output_path = args.output if args.output.is_absolute() else ROOT / args.output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
