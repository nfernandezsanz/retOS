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
DEFAULT_COVERAGE_TARGETS = {
    "branch_minimum_percent": 90.0,
    "last_recorded_branch_percent": 0.0,
    "last_recorded_total_percent": 0.0,
    "source": "fallback",
    "source_available": False,
    "source_path": "backend/coverage.json",
    "total_minimum_percent": 90.0,
}

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
    "docs/assets/retos-project-card.svg",
    "docs/auditor-evidence-matrix.md",
    "docs/production-readiness.md",
    "docs/release-process.md",
    "docs/operations.md",
    "docs/docker.md",
    "docs/branding.md",
    "frontend/public/retos-mark.svg",
    "frontend/src/styles.css",
    "frontend/e2e/app.spec.ts",
    "docs/releases/2026.06.28-alpha.1.md",
    "docs/releases/evidence/backup-restore-drill-template.md",
    "docs/releases/evidence/production-promotion-template.md",
    "docs/releases/evidence/target-security-review-template.md",
    "scripts/check_ci_status.sh",
    "scripts/check_auditor_evidence_matrix.sh",
    "scripts/check_audit_pack.sh",
    "scripts/check_backup_restore_drill.py",
    "scripts/check_env_security.py",
    "scripts/check_promotion_template.py",
    "scripts/check_target_security_review.py",
    "scripts/check_eval_calibration_evidence.py",
    "scripts/check_eval_calibration_trend.py",
    "scripts/check_production_preflight.sh",
    "scripts/check_release_workflow.sh",
    "scripts/check_published_release_evidence.sh",
    "scripts/check_visual_audit.py",
    "scripts/export_audit_manifest.py",
    "scripts/check_audit_handoff_report.py",
    "scripts/export_audit_handoff_report.py",
    "scripts/check_audit_bundle.py",
    "scripts/export_audit_bundle.py",
)

LOCAL_GATES = (
    "make local-acceptance",
    "make check",
    "make integration",
    "make frontend-test",
    "make frontend-e2e",
    "make frontend-visual-audit",
    "make visual-audit-check",
    "docker compose --env-file .env.example config",
    "docker compose --dry-run build",
    "make docker-smoke",
    "make release-check",
    "make production-preflight",
    "make auditor-static-check",
    "make audit-manifest-check",
    "make dependency-audit",
    "make security-policy-check",
    "make target-security-review-check",
    "make env-security-check",
    "make backup-restore-drill-check",
    "make promotion-template-check",
    "make ignore-hygiene-check",
    "make operations-runbook-check",
    "make auditor-evidence-matrix-check",
    "make release-workflow-check",
    "make release-notes-check",
    "make versioned-release-notes-check",
    "make eval-calibration-gate",
    "make eval-calibration-trend-gate",
    "make ci-status-check",
)

EXTERNAL_PROMOTION_EVIDENCE = (
    "GHCR backend and web digests from the immutable release workflow run",
    "SBOM/provenance attestations from GitHub Actions",
    "Cosign verification against published backend and web digests",
    "Accepted calibration scope or broader public-slice trend evidence",
    "Human target-environment security review",
    "Completed target security review evidence template",
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


def json_record(relative_path: str) -> dict[str, Any]:
    record = file_record(relative_path)
    if not record.get("exists"):
        return record
    try:
        record["json"] = json.loads((ROOT / relative_path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        record["json_error"] = str(exc)
    return record


def branch_coverage_minimum() -> float:
    makefile = ROOT / "Makefile"
    for line in makefile.read_text(encoding="utf-8").splitlines():
        if line.startswith("BRANCH_COVERAGE_MIN"):
            _, value = line.split("?=", maxsplit=1)
            return round(float(value.strip()), 2)
    return DEFAULT_COVERAGE_TARGETS["branch_minimum_percent"]


def coverage_targets() -> dict[str, Any]:
    coverage_path = ROOT / "backend" / "coverage.json"
    targets = {
        **DEFAULT_COVERAGE_TARGETS,
        "branch_minimum_percent": branch_coverage_minimum(),
    }
    if not coverage_path.is_file():
        targets["source_reason"] = "coverage report not found"
        return targets

    try:
        report = json.loads(coverage_path.read_text(encoding="utf-8"))
        totals = report["totals"]
        meta = report.get("meta", {})
        branch_percent = float(totals["percent_branches_covered"])
        total_percent = float(totals["percent_covered"])
        covered_branches = int(totals["covered_branches"])
        num_branches = int(totals["num_branches"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        targets["source_reason"] = f"coverage report could not be parsed: {exc}"
        return targets

    targets.update(
        {
            "branch_coverage_enabled": meta.get("branch_coverage") is True,
            "covered_branches": covered_branches,
            "last_recorded_branch_percent": round(branch_percent, 2),
            "last_recorded_total_percent": round(total_percent, 2),
            "num_branches": num_branches,
            "source": "coverage.py json",
            "source_available": True,
            "source_path": str(coverage_path.relative_to(ROOT)),
        }
    )
    return targets


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
    ci = (
        {"available": False, "reason": "CI lookup skipped by request", "skipped": True}
        if args.skip_ci_lookup
        else github_ci(args.repository, sha)
    )
    github_actions = os.environ.get("GITHUB_ACTIONS") == "true"
    github_run_id = os.environ.get("GITHUB_RUN_ID")
    generated_for_current_github_run = (
        github_actions
        and github_run_id is not None
        and str(ci.get("run_id")) == github_run_id
    )
    return {
        "ci": {
            **ci,
            "generated_for_current_github_run": generated_for_current_github_run,
            "post_run_ci_validation_required": generated_for_current_github_run,
            "post_run_ci_validation_command": "make ci-status-check",
        },
        "coverage_targets": coverage_targets(),
        "critical_file_hashes": [file_record(path) for path in CRITICAL_FILES],
        "external_promotion_evidence_required": list(EXTERNAL_PROMOTION_EVIDENCE),
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "generation_context": {
            "github_actions": github_actions,
            "github_job": os.environ.get("GITHUB_JOB"),
            "github_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
            "github_run_id": github_run_id,
            "mode": "github-actions-in-run" if github_actions else "local-or-operator",
            "note": (
                "When generated inside GitHub Actions, the manifest is an in-run snapshot. "
                "Treat the uploaded artifact as final evidence only together with a later "
                "`make ci-status-check` success for the same commit."
                if github_actions
                else "Operator-generated manifest after local or remote validation."
            ),
        },
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
            "local_manifest": json_record("frontend/visual-audit/manifest.json"),
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
    parser.add_argument(
        "--skip-ci-lookup",
        action="store_true",
        help="Skip the GitHub Actions API lookup while still validating manifest shape.",
    )
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
