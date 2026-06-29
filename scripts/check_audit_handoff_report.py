#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"Audit handoff report failed: {message}")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        manifest = tmp / "audit-manifest.json"
        report = tmp / "audit-handoff.md"
        subprocess.run(
            [
                "python3",
                "scripts/export_audit_manifest.py",
                "--skip-ci-lookup",
                "--output",
                str(manifest),
            ],
            cwd=ROOT,
            check=True,
        )
        subprocess.run(
            [
                "python3",
                "scripts/export_audit_handoff_report.py",
                "--manifest",
                str(manifest),
                "--output",
                str(report),
            ],
            cwd=ROOT,
            check=True,
        )
        content = report.read_text(encoding="utf-8")

    for phrase in (
        "# RetOS Audit Handoff Report",
        "## Candidate",
        "## Readiness Verdict",
        "## Local Gates To Reproduce",
        "## Remaining External Promotion Evidence",
        "## Promotion Decision Checklist",
        "## Critical Evidence Hashes",
        "## Visual Evidence",
        "## Auditor Notes",
        "Production promotion ready",
        "Coverage evidence source",
        "backend/coverage.json",
        "coverage.py json",
        "Candidate worktree is clean",
        "All critical evidence files exist",
        "Local visual audit manifest and desktop/mobile screenshots are present",
        "External GHCR digests, SBOM/provenance, and Cosign verification are recorded",
        "Target-environment human security review is complete",
        "Calibration scope decision template is completed",
        "make local-acceptance",
        "make auditor-static-check",
        "make ci-status-check",
        "GHCR backend and web digests",
        "SBOM/provenance",
        "Cosign verification",
        "docs/auditor-evidence-matrix.md",
        "docs/assets/retos-project-card.svg",
        "frontend/public/retos-mark.svg",
        "scripts/check_audit_handoff_report.py",
        "scripts/export_audit_handoff_report.py",
        "scripts/check_audit_bundle.py",
        "scripts/export_audit_bundle.py",
        "retos-visual-audit-",
        "calibration-scope-decision-template.md",
        "production-promotion-template.md",
    ):
        require(phrase in content, f"generated report missing phrase: {phrase}")

    print("Audit handoff report OK: Markdown summary preserves manifest evidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
