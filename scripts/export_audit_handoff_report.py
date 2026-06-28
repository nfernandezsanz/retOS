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
        f"| CI available in manifest | {status_text(ci.get('available'))} |",
        f"| CI status | `{ci.get('status', 'not available')}` |",
        f"| CI conclusion | `{ci.get('conclusion', 'not available')}` |",
        "",
        manifest["production_promotion_ready_reason"],
        "",
        "## Local Gates To Reproduce",
        "",
        *markdown_list(manifest["local_gates_required"]),
        "",
        "## Remaining External Promotion Evidence",
        "",
        *[f"- {item}" for item in manifest["external_promotion_evidence_required"]],
        "",
        "## Critical Evidence Hashes",
        "",
        "| Path | Present | SHA-256 |",
        "| --- | --- | --- |",
    ]

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
