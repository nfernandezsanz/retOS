#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(
            f"Audit handoff report failed: missing manifest {path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"Audit handoff report failed: invalid JSON in {path}"
        ) from exc


def status_text(value: object) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    if value is None:
        return "unknown"
    return str(value)


def markdown_list(items: list[str]) -> list[str]:
    return [f"- `{item}`" for item in items]


def checked(value: bool) -> str:
    return "x" if value else " "


def build_decision_checklist(
    manifest: dict[str, Any],
    *,
    missing_critical: list[str],
) -> list[str]:
    repository = manifest["repository"]
    ci = manifest["ci"]
    visual = manifest["visual_audit"]
    local_manifest = visual["local_manifest"]
    local_screenshots = visual["local_screenshots"]
    critical_files_present = not missing_critical
    visual_files_present = bool(local_manifest.get("exists")) and all(
        screenshot.get("exists") for screenshot in local_screenshots
    )
    ci_ready = (
        ci.get("available") is True
        and ci.get("status") == "completed"
        and ci.get("conclusion") == "success"
    )
    clean_worktree = repository["dirty"] is False

    return [
        f"- [{checked(clean_worktree)}] Candidate worktree is clean for `{repository['commit_sha']}`.",
        f"- [{checked(ci_ready)}] GitHub Actions CI is completed successfully for the candidate commit.",
        f"- [{checked(critical_files_present)}] All critical evidence files exist and have SHA-256 hashes.",
        f"- [{checked(visual_files_present)}] Local visual audit manifest and desktop/mobile screenshots are present.",
        "- [ ] External GHCR digests, SBOM/provenance, and Cosign verification are recorded.",
        "- [ ] Target-environment human security review is complete.",
        "- [ ] Calibration scope decision template is completed for bounded pilot acceptance or broader trend evidence.",
    ]


def build_evidence_status_rows(
    manifest: dict[str, Any],
    *,
    missing_critical: list[str],
) -> list[tuple[str, str, str]]:
    repository = manifest["repository"]
    ci = manifest["ci"]
    visual = manifest["visual_audit"]
    local_manifest = visual["local_manifest"]
    local_screenshots = visual["local_screenshots"]
    visual_files_present = bool(local_manifest.get("exists")) and all(
        screenshot.get("exists") for screenshot in local_screenshots
    )
    ci_available = ci.get("available") is True
    ci_ready = (
        ci_available
        and ci.get("status") == "completed"
        and ci.get("conclusion") == "success"
    )

    return [
        (
            "Local worktree",
            "ready" if repository["dirty"] is False else "review",
            (
                "Clean candidate checkout"
                if repository["dirty"] is False
                else "Dirty files must be reviewed before promotion"
            ),
        ),
        (
            "GitHub Actions",
            "ready" if ci_ready else "pending",
            (
                "Current commit CI is green"
                if ci_ready
                else ci.get(
                    "reason", "Run `make ci-status-check` for the candidate commit"
                )
            ),
        ),
        (
            "Critical files",
            "ready" if not missing_critical else "review",
            (
                "All required evidence files are hashed"
                if not missing_critical
                else f"{len(missing_critical)} required file(s) missing"
            ),
        ),
        (
            "Visual evidence",
            "ready" if visual_files_present else "review",
            (
                "Local manifest and desktop/mobile screenshots are present"
                if visual_files_present
                else "Run `make frontend-visual-audit` and `make visual-audit-check`"
            ),
        ),
        (
            "Local gates",
            "operator-run",
            f"{len(manifest['local_gates_required'])} reproducible local gate command(s) listed below",
        ),
        (
            "External release evidence",
            "pending",
            f"{len(manifest['external_promotion_evidence_required'])} item(s) still require registry, CI release, or human evidence",
        ),
    ]


def build_report(manifest: dict[str, Any], *, manifest_path: Path) -> str:
    repository = manifest["repository"]
    coverage = manifest["coverage_targets"]
    ci = manifest["ci"]
    generation = manifest["generation_context"]
    visual = manifest["visual_audit"]
    critical_files = manifest["critical_file_hashes"]
    missing_critical = [
        record["path"] for record in critical_files if not record.get("exists")
    ]

    lines: list[str] = [
        "# RetOS Audit Handoff Report",
        "",
        "This report is generated from the local audit manifest. It is a human-readable",
        "companion to the JSON handoff and does not replace release publishing evidence.",
        "",
        "## Candidate",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Commit | `{repository['commit_sha']}` |",
        f"| Branch | `{repository.get('branch') or 'unknown'}` |",
        f"| Remote | `{repository.get('remote') or 'unknown'}` |",
        f"| Dirty worktree | {status_text(repository['dirty'])} |",
        f"| Manifest | `{manifest_path}` |",
        f"| Generated at | `{manifest['generated_at']}` |",
        f"| Generation mode | `{generation['mode']}` |",
        "",
        "## Readiness Verdict",
        "",
        "| Signal | Value |",
        "| --- | --- |",
        f"| Production promotion ready | {status_text(manifest['production_promotion_ready'])} |",
        f"| Total coverage recorded | {coverage['last_recorded_total_percent']:.2f}% |",
        f"| Branch coverage recorded | {coverage['last_recorded_branch_percent']:.2f}% |",
        f"| Coverage evidence source | `{coverage.get('source_path', 'unknown')}` ({coverage.get('source', 'unknown')}) |",
        f"| CI available in manifest | {status_text(ci.get('available'))} |",
        f"| CI status | `{ci.get('status', 'not available')}` |",
        f"| CI conclusion | `{ci.get('conclusion', 'not available')}` |",
        "",
        manifest["production_promotion_ready_reason"],
        "",
        "## Evidence Status",
        "",
        "| Area | Status | Notes |",
        "| --- | --- | --- |",
    ]

    lines.extend(
        f"| {area} | `{status}` | {notes} |"
        for area, status, notes in build_evidence_status_rows(
            manifest, missing_critical=missing_critical
        )
    )

    lines.extend(
        [
            "",
            "## Local Gates To Reproduce",
            "",
            *markdown_list(manifest["local_gates_required"]),
            "",
            "## Remaining External Promotion Evidence",
            "",
            *[f"- {item}" for item in manifest["external_promotion_evidence_required"]],
            "",
            "## Promotion Decision Checklist",
            "",
            *build_decision_checklist(manifest, missing_critical=missing_critical),
            "",
            "## Critical Evidence Hashes",
            "",
            "| Path | Present | SHA-256 |",
            "| --- | --- | --- |",
        ]
    )

    for record in critical_files:
        digest = record.get("sha256", "missing")
        lines.append(
            f"| `{record['path']}` | {status_text(record.get('exists'))} | `{digest}` |"
        )

    lines.extend(
        [
            "",
            "## Visual Evidence",
            "",
            f"- CI visual artifact: `{visual['ci_artifact']}`",
            f"- Release visual artifact: `{visual['release_artifact']}`",
            f"- Local visual manifest: `{visual['local_manifest']['path']}`",
        ]
    )
    for screenshot in visual["local_screenshots"]:
        digest = screenshot.get("sha256", "missing")
        lines.append(
            f"- `{screenshot['path']}` present={status_text(screenshot.get('exists'))} "
            f"sha256=`{digest}`"
        )

    lines.extend(
        [
            "",
            "## Auditor Notes",
            "",
            "- Treat this report as local handoff evidence, not final production promotion.",
            "- Pair GitHub Actions generated manifests with `make ci-status-check` for the same commit.",
            "- Complete `docs/releases/evidence/calibration-scope-decision-template.md` when relying on bounded public calibration slices.",
            "- Complete `docs/releases/evidence/production-promotion-template.md` for the target environment.",
        ]
    )
    if missing_critical:
        lines.extend(
            [
                "",
                "## Missing Critical Files",
                "",
                *[f"- `{path}`" for path in missing_critical],
            ]
        )

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export a human-readable RetOS audit handoff report from the JSON manifest."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("evals/reports/audit-manifest.json"),
        help="Path to a JSON manifest generated by scripts/export_audit_manifest.py.",
    )
    parser.add_argument(
        "--output", type=Path, help="Write the Markdown report to this path."
    )
    args = parser.parse_args()

    manifest_path = (
        args.manifest if args.manifest.is_absolute() else ROOT / args.manifest
    )
    manifest = load_manifest(manifest_path)
    report = build_report(manifest, manifest_path=manifest_path)
    if args.output:
        output = args.output if args.output.is_absolute() else ROOT / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(report, encoding="utf-8")
    else:
        sys.stdout.write(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
