#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import subprocess
import tarfile
import tempfile
from pathlib import Path

from export_audit_bundle import BUNDLE_ROOT, ROOT

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
    f"{BUNDLE_ROOT}/docs/releases/evidence/production-promotion-template.md",
    f"{BUNDLE_ROOT}/.github/workflows/ci.yml",
    f"{BUNDLE_ROOT}/.github/workflows/release.yml",
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

    missing = sorted(REQUIRED_MEMBERS - members)
    require(not missing, f"bundle missing required member(s): {', '.join(missing)}")
    if (ROOT / "frontend/visual-audit/manifest.json").is_file():
        require(
            any(
                name.endswith("frontend/visual-audit/manifest.json") for name in members
            ),
            "bundle should include local visual audit manifest when present",
        )
    print(
        "Audit bundle OK: archive, checksum, manifest, report, and evidence docs are aligned."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
