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
    "docs/releases/evidence/calibration-scope-decision-template.md",
    "docs/releases/evidence/backup-restore-drill-template.md",
    "docs/releases/evidence/target-security-review-template.md",
    "docs/releases/evidence/visual-review-template.md",
    "scripts/check_readme_usability.py",
    "scripts/check_visual_review.py",
    "scripts/check_ci_workflow.sh",
    "scripts/check_ci_status.sh",
    "scripts/check_auditor_evidence_matrix.sh",
    "scripts/check_audit_pack.sh",
    "scripts/check_backup_restore_drill.py",
    "scripts/check_env_security.py",
    "scripts/check_promotion_template.py",
    "scripts/check_target_security_review.py",
    "scripts/check_calibration_scope_decision.py",
    "scripts/check_eval_calibration_evidence.py",
    "scripts/check_eval_calibration_trend.py",
    "scripts/check_visual_audit.py",
    "scripts/check_audit_handoff_report.py",
    "scripts/check_audit_bundle.py",
    "scripts/export_audit_manifest.py",
    "scripts/export_audit_handoff_report.py",
    "scripts/export_audit_bundle.py",
}
REQUIRED_LOCAL_GATES = {
    "make local-acceptance",
    "make check",
    "make integration",
    "make frontend-visual-audit",
    "make visual-audit-check",
    "make docker-smoke",
    "make auditor-evidence-matrix-check",
    "make auditor-static-check",
    "make audit-manifest-check",
    "make env-security-check",
    "make target-security-review-check",
    "make visual-review-check",
    "make backup-restore-drill-check",
    "make promotion-template-check",
    "make eval-calibration-gate",
    "make eval-calibration-trend-gate",
    "make calibration-scope-decision-check",
    "make ci-status-check",
}
EXPECTED_VISUAL_SECTIONS = [
    "Overview",
    "Documents",
    "Queries",
    "Evals",
    "Audit",
    "Admin",
]
EXPECTED_VISUAL_MODULES = [
    "documents-library",
    "documents-sources",
    "documents-upload",
    "documents-text",
    "queries-runner",
    "queries-live",
    "evals-runner",
    "evals-results",
    "evals-history",
    "audit-jobs",
    "audit-progress",
    "audit-events",
    "admin-providers",
    "admin-users",
]
EXPECTED_VISUAL_RESPONSIVE_WIDTHS = [375, 768, 1024, 1440]
MIN_VISUAL_TOOLTIP_TARGETS = 10


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


def validate_visual_manifest_json(manifest_json: dict[str, Any]) -> None:
    coverage = manifest_json.get("coverage")
    require(isinstance(coverage, dict), "visual audit manifest must include coverage")
    require(
        coverage.get("sections") == EXPECTED_VISUAL_SECTIONS,
        "visual audit coverage must record expected workspace sections",
    )
    require(
        coverage.get("visible_sections") == EXPECTED_VISUAL_SECTIONS,
        "visual audit coverage must record visible workspace sections",
    )
    require(
        coverage.get("modules") == EXPECTED_VISUAL_MODULES,
        "visual audit coverage must record expected workspace modules",
    )
    tooltip_targets = coverage.get("tooltip_targets")
    require(
        isinstance(tooltip_targets, int)
        and tooltip_targets >= MIN_VISUAL_TOOLTIP_TARGETS,
        "visual audit coverage must record tooltip targets",
    )
    require(
        coverage.get("no_horizontal_overflow") is True,
        "visual audit coverage must record no horizontal overflow",
    )
    responsive_checks = coverage.get("responsive_checks")
    require(
        isinstance(responsive_checks, list),
        "visual audit coverage must record responsive checks",
    )
    by_width = {
        record.get("width"): record
        for record in responsive_checks
        if isinstance(record, dict) and record.get("width")
    }
    missing_widths = sorted(set(EXPECTED_VISUAL_RESPONSIVE_WIDTHS) - set(by_width))
    require(
        not missing_widths,
        "visual audit coverage missing responsive width(s): "
        + ", ".join(str(width) for width in missing_widths),
    )
    for width in EXPECTED_VISUAL_RESPONSIVE_WIDTHS:
        record = by_width[width]
        require(
            record.get("height") == 900,
            f"visual audit responsive width {width} must use height 900",
        )
        require(
            record.get("no_horizontal_overflow") is True,
            f"visual audit responsive width {width} must record no overflow",
        )


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
    require(
        coverage["source_path"] == "backend/coverage.json",
        "coverage evidence must point at backend/coverage.json",
    )
    if coverage["source_available"]:
        require(
            coverage["source"] == "coverage.py json",
            "available coverage evidence must come from coverage.py JSON",
        )
        require(
            coverage["branch_coverage_enabled"] is True,
            "coverage evidence must include branch coverage",
        )
        require(
            coverage["last_recorded_total_percent"]
            >= coverage["total_minimum_percent"],
            "recorded total coverage must meet the total target",
        )
        require(
            coverage["last_recorded_branch_percent"]
            >= coverage["branch_minimum_percent"],
            "recorded branch coverage must meet the branch target",
        )
        require(
            coverage["covered_branches"] <= coverage["num_branches"],
            "coverage branch counters must be internally consistent",
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
        validate_visual_manifest_json(local_manifest["json"])
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
        "Audit manifest OK: schema, gates, hashes, visual coverage, artifacts, and blockers are aligned."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
