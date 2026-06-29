from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


def load_handoff_exporter() -> ModuleType:
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "export_audit_handoff_report.py"
    spec = importlib.util.spec_from_file_location("export_audit_handoff_report", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load audit handoff exporter from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def manifest_fixture(
    *,
    dirty: bool = False,
    ci_success: bool = True,
    missing_critical: bool = False,
    visual_present: bool = True,
) -> dict[str, Any]:
    return {
        "repository": {
            "commit_sha": "abc123def456",
            "branch": "main",
            "remote": "git@github.com:nfernandezsanz/retOS.git",
            "dirty": dirty,
        },
        "coverage_targets": {
            "last_recorded_total_percent": 95.43,
            "last_recorded_branch_percent": 90.78,
            "source_path": "backend/coverage.json",
            "source": "coverage.py json",
        },
        "ci": {
            "available": ci_success,
            "status": "completed" if ci_success else "not_found",
            "conclusion": "success" if ci_success else None,
            "reason": "No current CI run found",
        },
        "generation_context": {"mode": "local-or-operator"},
        "visual_audit": {
            "ci_artifact": "retos-visual-audit-abc123def456",
            "release_artifact": "retos-release-visual-audit",
            "local_manifest": {
                "path": "frontend/visual-audit/manifest.json",
                "exists": visual_present,
            },
            "local_screenshots": [
                {
                    "path": "frontend/visual-audit/retos-console-desktop.png",
                    "exists": visual_present,
                    "sha256": "desktop-sha",
                },
                {
                    "path": "frontend/visual-audit/retos-console-mobile.png",
                    "exists": visual_present,
                    "sha256": "mobile-sha",
                },
            ],
        },
        "critical_file_hashes": [
            {
                "path": "README.md",
                "exists": not missing_critical,
                "sha256": "readme-sha" if not missing_critical else "missing",
            },
            {
                "path": "docs/production-readiness.md",
                "exists": True,
                "sha256": "readiness-sha",
            },
        ],
        "local_gates_required": ["make check", "make local-acceptance"],
        "external_promotion_evidence_required": [
            "GHCR backend and web digests",
            "SBOM/provenance",
            "Cosign verification",
        ],
        "production_promotion_ready": False,
        "production_promotion_ready_reason": (
            "Promotion still requires immutable release publishing evidence and human review."
        ),
        "generated_at": "2026-06-29T12:00:00Z",
    }


def test_build_report_marks_complete_local_evidence_ready() -> None:
    exporter = load_handoff_exporter()

    report = exporter.build_report(
        manifest_fixture(),
        manifest_path=Path("evals/reports/audit-manifest.json"),
    )

    assert "# RetOS Audit Handoff Report" in report
    assert "| Local worktree | `ready` | Clean candidate checkout |" in report
    assert "| GitHub Actions | `ready` | Current commit CI is green |" in report
    assert "| Critical files | `ready` | All required evidence files are hashed |" in report
    assert (
        "| Visual evidence | `ready` | Local manifest and desktop/mobile screenshots are present |"
        in report
    )
    assert "- [x] Candidate worktree is clean for `abc123def456`." in report
    assert "- [x] GitHub Actions CI is completed successfully for the candidate commit." in report
    assert "- [x] All critical evidence files exist and have SHA-256 hashes." in report
    assert (
        "- [ ] External GHCR digests, SBOM/provenance, and Cosign verification are recorded."
        in report
    )
    assert "- `make local-acceptance`" in report
    assert "- GHCR backend and web digests" in report


def test_build_report_surfaces_dirty_missing_or_incomplete_evidence() -> None:
    exporter = load_handoff_exporter()

    report = exporter.build_report(
        manifest_fixture(
            dirty=True,
            ci_success=False,
            missing_critical=True,
            visual_present=False,
        ),
        manifest_path=Path("evals/reports/audit-manifest.json"),
    )

    assert "| Local worktree | `review` | Dirty files must be reviewed before promotion |" in report
    assert "| GitHub Actions | `pending` | No current CI run found |" in report
    assert "| Critical files | `review` | 1 required file(s) missing |" in report
    expected_visual_review = (
        "| Visual evidence | `review` | Run `make frontend-visual-audit` "
        "and `make visual-audit-check` |"
    )
    assert expected_visual_review in report
    assert "- [ ] Candidate worktree is clean for `abc123def456`." in report
    assert "- [ ] GitHub Actions CI is completed successfully for the candidate commit." in report
    assert "- [ ] All critical evidence files exist and have SHA-256 hashes." in report
    assert "## Missing Critical Files" in report
    assert "- `README.md`" in report
