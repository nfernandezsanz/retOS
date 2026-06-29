#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_TOP_LEVEL_KEYS = {
    "ci",
    "coverage_targets",
    "critical_file_hashes",
    "external_promotion_evidence_required",
    "generated_at",
    "generation_context",
    "local_gates_required",
    "production_promotion_ready",
    "production_promotion_ready_reason",
    "repository",
    "schema_version",
    "visual_audit",
}
REQUIRED_CRITICAL_FILES = {
    "README.md",
    ".github/workflows/ci.yml",
    ".github/workflows/release.yml",
    "docs/assets/retos-project-card.svg",
    "docs/auditor-evidence-matrix.md",
    "docs/branding.md",
    "docs/production-readiness.md",
    "frontend/public/retos-mark.svg",
    "frontend/src/styles.css",
    "frontend/e2e/app.spec.ts",
    "docs/releases/2026.06.28-alpha.1.md",
    "scripts/check_ci_status.sh",
    "scripts/check_auditor_evidence_matrix.sh",
    "scripts/check_audit_pack.sh",
    "scripts/check_audit_handoff_report.py",
    "scripts/export_audit_manifest.py",
    "scripts/export_audit_handoff_report.py",
}
REQUIRED_LOCAL_GATES = {
    "make check",
    "make integration",
    "make frontend-visual-audit",
    "make docker-smoke",
    "make auditor-evidence-matrix-check",
    "make auditor-static-check",
    "make audit-manifest-check",
    "make ci-status-check",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"Audit manifest failed: {message}")


def load_manifest() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "audit-manifest.json"
        env = os.environ.copy()
        for key in (
            "GITHUB_ACTIONS",
            "GITHUB_JOB",
            "GITHUB_RUN_ATTEMPT",
            "GITHUB_RUN_ID",
        ):
            env.pop(key, None)
        subprocess.run(
            [
                "python3",
                "scripts/export_audit_manifest.py",
                "--skip-ci-lookup",
                "--output",
                str(output),
            ],
            cwd=ROOT,
            env=env,
            check=True,
        )
        return json.loads(output.read_text(encoding="utf-8"))


def main() -> int:
    manifest = load_manifest()
    missing_keys = REQUIRED_TOP_LEVEL_KEYS - set(manifest)
    require(
        not missing_keys, f"missing top-level key(s): {', '.join(sorted(missing_keys))}"
    )
    require(manifest["schema_version"] == 1, "schema_version must be 1")
    require(
        manifest["production_promotion_ready"] is False,
        "manifest must not claim production promotion",
    )
    require(
        "immutable release publishing evidence"
        in manifest["production_promotion_ready_reason"],
        "promotion readiness reason must keep external release evidence explicit",
    )

    ci = manifest["ci"]
    require(
        ci["available"] is False and ci["skipped"] is True,
        "offline check must skip CI lookup",
    )
    require(
        ci["post_run_ci_validation_required"] is False,
        "offline check must not require post-run validation",
    )
    require(
        ci["post_run_ci_validation_command"] == "make ci-status-check",
        "CI validation command must be stable",
    )

    generation = manifest["generation_context"]
    require(
        generation["mode"] == "local-or-operator",
        "offline check must use local generation mode",
    )
    require(
        generation["github_actions"] is False,
        "offline check must not look like GitHub Actions",
    )

    coverage = manifest["coverage_targets"]
    require(
        coverage["total_minimum_percent"] >= 90,
        "total coverage target must stay at least 90%",
    )
    require(
        coverage["branch_minimum_percent"] >= 90,
        "branch coverage target must stay at least 90%",
    )

    critical_files = manifest["critical_file_hashes"]
    by_path = {record["path"]: record for record in critical_files}
    missing_files = REQUIRED_CRITICAL_FILES - set(by_path)
    require(
        not missing_files,
        f"missing critical file hash(es): {', '.join(sorted(missing_files))}",
    )
    for path in REQUIRED_CRITICAL_FILES:
        record = by_path[path]
        require(record["exists"] is True, f"critical file must exist: {path}")
        require(
            len(record["sha256"]) == 64, f"critical file hash must be sha256: {path}"
        )
        require(record["size_bytes"] > 0, f"critical file must not be empty: {path}")

    gates = set(manifest["local_gates_required"])
    missing_gates = REQUIRED_LOCAL_GATES - gates
    require(
        not missing_gates, f"missing local gate(s): {', '.join(sorted(missing_gates))}"
    )

    visual = manifest["visual_audit"]
    require(
        "retos-visual-audit-" in visual["ci_artifact"],
        "visual CI artifact name must be present",
    )
    require(
        "retos-release-visual-audit-" in visual["release_artifact"],
        "visual release artifact name must be present",
    )
    local_manifest = visual["local_manifest"]
    require(
        "frontend/visual-audit/manifest.json" == local_manifest["path"],
        "visual audit manifest path must be stable",
    )
    if local_manifest["exists"]:
        require(
            len(local_manifest["sha256"]) == 64,
            "visual audit manifest must have a sha256 hash",
        )
        require(
            "json" in local_manifest and "json_error" not in local_manifest,
            "visual audit manifest must be valid JSON when present",
        )
        screenshots = local_manifest["json"].get("screenshots", [])
        by_name = {record.get("name"): record for record in screenshots}
        require(
            {"desktop", "mobile"} <= set(by_name),
            "visual audit manifest must include desktop and mobile screenshots",
        )
        for name, expected_path in (
            ("desktop", "visual-audit/retos-console-desktop.png"),
            ("mobile", "visual-audit/retos-console-mobile.png"),
        ):
            record = by_name[name]
            require(
                record.get("path") == expected_path,
                f"{name} screenshot path must be stable",
            )
            require(
                len(record.get("sha256", "")) == 64,
                f"{name} screenshot must include sha256",
            )
            require(
                record.get("size_bytes", 0) > 0, f"{name} screenshot must not be empty"
            )
            viewport = record.get("viewport", {})
            require(
                viewport.get("width", 0) > 0 and viewport.get("height", 0) > 0,
                f"{name} screenshot must record viewport dimensions",
            )

    external = "\n".join(manifest["external_promotion_evidence_required"])
    for phrase in (
        "GHCR",
        "SBOM/provenance",
        "Cosign",
        "Human target-environment security review",
    ):
        require(phrase in external, f"external promotion evidence missing {phrase}")

    print(
        "Audit manifest OK: schema, gates, hashes, visual artifacts, and blockers are aligned."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
