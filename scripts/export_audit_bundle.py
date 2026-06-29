#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import subprocess
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUNDLE_ROOT = "retos-audit-handoff"

STATIC_EVIDENCE_FILES = (
    "README.md",
    "CHANGELOG.md",
    "SECURITY.md",
    "docs/auditor-evidence-matrix.md",
    "docs/branding.md",
    "docs/operations.md",
    "docs/production-readiness.md",
    "docs/release-process.md",
    "docs/releases/2026.06.28-alpha.1.md",
    "docs/releases/evidence/2026.06.28-alpha.1-calibration.md",
    "docs/releases/evidence/2026.06.28-alpha.1-calibration-trend.md",
    "docs/releases/evidence/calibration-scope-decision-template.md",
    "docs/releases/evidence/backup-restore-drill-template.md",
    "docs/releases/evidence/production-promotion-template.md",
    "docs/releases/evidence/target-security-review-template.md",
    ".github/workflows/ci.yml",
    ".github/workflows/release.yml",
    "scripts/check_readme_usability.py",
    "scripts/check_ci_workflow.sh",
)

OPTIONAL_EVIDENCE_FILES = (
    "frontend/visual-audit/manifest.json",
    "frontend/visual-audit/retos-console-desktop.png",
    "frontend/visual-audit/retos-console-mobile.png",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def add_file(tar: tarfile.TarFile, path: Path, arcname: str) -> None:
    tar.add(path, arcname=f"{BUNDLE_ROOT}/{arcname}", recursive=False)


def export_generated_evidence(tmp: Path, skip_ci_lookup: bool) -> tuple[Path, Path]:
    manifest = tmp / "audit-manifest.json"
    handoff = tmp / "audit-handoff.md"
    manifest_command = [
        "python3",
        "scripts/export_audit_manifest.py",
        "--output",
        str(manifest),
    ]
    if skip_ci_lookup:
        manifest_command.insert(2, "--skip-ci-lookup")
    subprocess.run(manifest_command, cwd=ROOT, check=True)
    subprocess.run(
        [
            "python3",
            "scripts/export_audit_handoff_report.py",
            "--manifest",
            str(manifest),
            "--output",
            str(handoff),
        ],
        cwd=ROOT,
        check=True,
    )
    return manifest, handoff


def export_bundle(output: Path, skip_ci_lookup: bool) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest, handoff = export_generated_evidence(Path(tmpdir), skip_ci_lookup)
        with tarfile.open(output, "w:gz") as tar:
            add_file(tar, manifest, "evals/reports/audit-manifest.json")
            add_file(tar, handoff, "evals/reports/audit-handoff.md")
            for relative in STATIC_EVIDENCE_FILES:
                path = ROOT / relative
                if not path.is_file():
                    raise SystemExit(
                        f"Audit bundle failed: missing required file {relative}"
                    )
                add_file(tar, path, relative)
            for relative in OPTIONAL_EVIDENCE_FILES:
                path = ROOT / relative
                if path.is_file():
                    add_file(tar, path, relative)

    checksum_path = output.with_suffix(output.suffix + ".sha256")
    checksum_path.write_text(f"{sha256(output)}  {output.name}\n", encoding="utf-8")
    return checksum_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export a local RetOS audit handoff bundle."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evals/reports/retos-audit-handoff.tar.gz"),
        help="Path to the generated .tar.gz bundle.",
    )
    parser.add_argument(
        "--skip-ci-lookup",
        action="store_true",
        help="Skip GitHub Actions lookup when generating the bundled manifest.",
    )
    args = parser.parse_args()

    output = args.output if args.output.is_absolute() else ROOT / args.output
    checksum = export_bundle(output, skip_ci_lookup=args.skip_ci_lookup)
    print(f"Audit bundle written: {output}")
    print(f"Audit bundle sha256: {checksum}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
