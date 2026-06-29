#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import Any

from export_audit_bundle import BUNDLE_ROOT, ROOT

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
EXPECTED_VISUAL_HANDOFF_SUMMARY = "Visual coverage: ready - 6 section(s), 14 module(s)"
EXPECTED_VISUAL_HANDOFF_WIDTHS = "no-overflow widths: 375, 768, 1024, 1440"

REQUIRED_MEMBERS = {
    f"{BUNDLE_ROOT}/evals/reports/audit-manifest.json",
    f"{BUNDLE_ROOT}/evals/reports/audit-handoff.md",
    f"{BUNDLE_ROOT}/README.md",
    f"{BUNDLE_ROOT}/CHANGELOG.md",
    f"{BUNDLE_ROOT}/SECURITY.md",
    f"{BUNDLE_ROOT}/docs/auditor-evidence-matrix.md",
    f"{BUNDLE_ROOT}/docs/branding.md",
    f"{BUNDLE_ROOT}/docs/operations.md",
    f"{BUNDLE_ROOT}/docs/production-readiness.md",
    f"{BUNDLE_ROOT}/docs/release-process.md",
    f"{BUNDLE_ROOT}/docs/releases/2026.06.28-alpha.1.md",
    f"{BUNDLE_ROOT}/docs/releases/evidence/2026.06.28-alpha.1-calibration.md",
    f"{BUNDLE_ROOT}/docs/releases/evidence/2026.06.28-alpha.1-calibration-trend.md",
    f"{BUNDLE_ROOT}/docs/releases/evidence/calibration-scope-decision-template.md",
    f"{BUNDLE_ROOT}/docs/releases/evidence/backup-restore-drill-template.md",
    f"{BUNDLE_ROOT}/docs/releases/evidence/production-promotion-template.md",
    f"{BUNDLE_ROOT}/docs/releases/evidence/target-security-review-template.md",
    f"{BUNDLE_ROOT}/docs/releases/evidence/visual-review-template.md",
    f"{BUNDLE_ROOT}/.github/workflows/ci.yml",
    f"{BUNDLE_ROOT}/.github/workflows/release.yml",
    f"{BUNDLE_ROOT}/scripts/check_readme_usability.py",
    f"{BUNDLE_ROOT}/scripts/check_visual_review.py",
    f"{BUNDLE_ROOT}/scripts/check_ci_workflow.sh",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"Audit bundle failed: {message}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_member_text(tar: tarfile.TarFile, name: str) -> str:
    member = tar.getmember(name)
    handle = tar.extractfile(member)
    require(handle is not None, f"bundle member cannot be read: {name}")
    return handle.read().decode("utf-8")


def validate_visual_bundle_evidence(
    manifest: dict[str, Any],
    handoff: str,
    *,
    visual_manifest_bundled: bool,
) -> None:
    local_manifest = manifest["visual_audit"]["local_manifest"]
    if not local_manifest.get("exists"):
        return

    require(
        visual_manifest_bundled,
        "bundle should include local visual audit manifest when present",
    )
    require(
        EXPECTED_VISUAL_HANDOFF_SUMMARY in handoff
        and EXPECTED_VISUAL_HANDOFF_WIDTHS in handoff,
        "bundled handoff report must summarize visual audit coverage",
    )
    coverage = local_manifest.get("json", {}).get("coverage")
    require(isinstance(coverage, dict), "bundled manifest must include visual coverage")
    sections = coverage.get("sections", [])
    visible_sections = coverage.get("visible_sections", sections)
    for section in EXPECTED_VISUAL_SECTIONS:
        require(
            section in sections and section in visible_sections,
            f"bundled visual coverage missing section: {section}",
        )
    modules = coverage.get("modules", [])
    for module in EXPECTED_VISUAL_MODULES:
        require(
            module in modules,
            f"bundled visual coverage missing module: {module}",
        )
    require(
        int(coverage.get("tooltip_targets", 0)) >= MIN_VISUAL_TOOLTIP_TARGETS,
        "bundled visual coverage must include tooltip targets",
    )
    require(
        coverage.get("no_horizontal_overflow") is True,
        "bundled visual coverage must record no horizontal overflow",
    )
    responsive_checks = coverage.get("responsive_checks", [])
    require(
        isinstance(responsive_checks, list),
        "bundled visual coverage must include responsive checks",
    )
    responsive_widths = {
        int(check.get("width", 0))
        for check in responsive_checks
        if isinstance(check, dict) and check.get("no_horizontal_overflow") is True
    }
    for width in EXPECTED_VISUAL_RESPONSIVE_WIDTHS:
        require(
            width in responsive_widths,
            f"bundled visual coverage missing responsive width: {width}",
        )


def main() -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        output = Path(tmpdir) / "retos-audit-handoff.tar.gz"

        subprocess.run(
            [
                "python3",
                "scripts/export_audit_bundle.py",
                "--skip-ci-lookup",
                "--output",
                str(output),
            ],
            cwd=ROOT,
            check=True,
        )
        checksum_path = output.with_suffix(output.suffix + ".sha256")
        require(
            output.is_file() and output.stat().st_size > 0, "bundle must be non-empty"
        )
        require(
            checksum_path.is_file() and checksum_path.stat().st_size > 0,
            "bundle checksum sidecar must be non-empty",
        )
        recorded_checksum = checksum_path.read_text(encoding="utf-8").split()[0]
        require(
            recorded_checksum == sha256(output), "checksum sidecar must match bundle"
        )
        with tarfile.open(output, "r:gz") as tar:
            members = {member.name for member in tar.getmembers() if member.isfile()}
            manifest_text = read_member_text(
                tar, f"{BUNDLE_ROOT}/evals/reports/audit-manifest.json"
            )
            handoff = read_member_text(
                tar, f"{BUNDLE_ROOT}/evals/reports/audit-handoff.md"
            )
            production = read_member_text(
                tar, f"{BUNDLE_ROOT}/docs/production-readiness.md"
            )
            promotion_template = read_member_text(
                tar,
                f"{BUNDLE_ROOT}/docs/releases/evidence/production-promotion-template.md",
            )
            calibration = read_member_text(
                tar,
                f"{BUNDLE_ROOT}/docs/releases/evidence/2026.06.28-alpha.1-calibration.md",
            )
            calibration_trend = read_member_text(
                tar,
                f"{BUNDLE_ROOT}/docs/releases/evidence/2026.06.28-alpha.1-calibration-trend.md",
            )

    missing = sorted(REQUIRED_MEMBERS - members)
    require(not missing, f"bundle missing required member(s): {', '.join(missing)}")
    manifest = json.loads(manifest_text)
    require(
        "make local-acceptance" in manifest["local_gates_required"],
        "bundled manifest must require make local-acceptance",
    )
    for name, content in (
        ("audit handoff report", handoff),
        ("production readiness pack", production),
        ("promotion template", promotion_template),
    ):
        require(
            "make local-acceptance" in content,
            f"bundled {name} must mention make local-acceptance",
        )
    require(
        "Status: PASS" in calibration and "Max records | 200" in calibration,
        "bundled calibration evidence must include passing 200-record evidence",
    )
    require(
        "Status: PASS" in calibration_trend
        and "Allowed regression tolerance: 0" in calibration_trend,
        "bundled calibration trend must include passing zero-regression evidence",
    )
    require(
        "Promotion Decision Checklist" in handoff,
        "bundled handoff report must include the promotion decision checklist",
    )
    require(
        "Evidence Status" in handoff and "External release evidence" in handoff,
        "bundled handoff report must include the evidence status summary",
    )
    validate_visual_bundle_evidence(
        manifest,
        handoff,
        visual_manifest_bundled=any(
            name.endswith("frontend/visual-audit/manifest.json") for name in members
        ),
    )
    print(
        "Audit bundle OK: archive, checksum, manifest, report, visual coverage, and evidence docs are aligned."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
