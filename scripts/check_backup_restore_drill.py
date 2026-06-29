#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = ROOT / "docs/releases/evidence/backup-restore-drill-template.md"

REQUIRED_HEADINGS = (
    "# Backup And Restore Drill Evidence Template",
    "## Candidate",
    "## Backup Evidence",
    "## Restore Evidence",
    "## Health Evidence",
    "## Audit Evidence",
    "## Decision",
)

REQUIRED_FIELDS = (
    "Release version",
    "Commit SHA",
    "Image tag",
    "Environment",
    "Compose project",
    "Operator",
    "Drill date",
    "Backup timestamp",
    "Backup directory",
    "Postgres dump path",
    "Postgres dump size",
    "Storage archive path",
    "Storage archive size",
    "Eval reports archive path",
    "Eval reports archive size",
    "Eval datasets archive path",
    "Eval datasets archive size",
    "Search index archive path",
    "Search index archive size",
    "Backup checksum command",
    "Backup checksum output",
    "Disposable restore environment",
    "Restore source backup",
    "`docker compose stop api worker web` output",
    "Postgres restore command",
    "Postgres restore output",
    "Storage restore output",
    "Eval reports restore output",
    "Eval datasets restore output",
    "Search index restore output",
    "`docker compose run --rm migrate migrate` output",
    "`docker compose up -d api worker web` output",
    "`curl --fail http://localhost:8000/healthz` output",
    "`curl --fail http://localhost:8000/readyz` output",
    "`curl --fail http://localhost:8000/versionz` output",
    "`curl --fail http://localhost:8080/` output",
    "`make api-smoke` output",
    "`make audit-export-check EXPORT=retos-audit-export.json` output",
    "Index rebuild decision",
    "`/audit/export` file",
    "`/audit/export` head hash",
    "Journal event count",
    "Progress event count",
    "Continuity gaps",
    "Validation failures",
    "Drill result",
    "Data loss observed",
    "Rollback required",
    "Follow-up issues",
    "Promotion impact",
)


class BackupRestoreDrillError(RuntimeError):
    pass


@dataclass(frozen=True)
class BackupRestoreDrillResult:
    headings: int
    fields: int


def _missing(required: tuple[str, ...], content: str) -> list[str]:
    return [item for item in required if item not in content]


def validate_backup_restore_drill(
    template_path: Path = DEFAULT_TEMPLATE,
) -> BackupRestoreDrillResult:
    if not template_path.is_file():
        raise BackupRestoreDrillError(f"backup/restore drill template not found: {template_path}")
    content = template_path.read_text(encoding="utf-8")
    if not content.strip():
        raise BackupRestoreDrillError("backup/restore drill template is empty")

    missing_headings = _missing(REQUIRED_HEADINGS, content)
    if missing_headings:
        raise BackupRestoreDrillError(
            "missing heading(s): " + ", ".join(missing_headings)
        )

    missing_fields = _missing(REQUIRED_FIELDS, content)
    if missing_fields:
        raise BackupRestoreDrillError(
            "missing evidence field(s): " + ", ".join(missing_fields)
        )

    if "completed copy with the production promotion evidence" not in content:
        raise BackupRestoreDrillError(
            "template must tell reviewers where the completed drill evidence is stored"
        )

    return BackupRestoreDrillResult(
        headings=len(REQUIRED_HEADINGS),
        fields=len(REQUIRED_FIELDS),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the RetOS backup/restore drill evidence template."
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=DEFAULT_TEMPLATE,
        help="Path to docs/releases/evidence/backup-restore-drill-template.md.",
    )
    args = parser.parse_args()
    try:
        result = validate_backup_restore_drill(args.template)
    except BackupRestoreDrillError as exc:
        print(f"Backup/restore drill failed: {exc}", file=sys.stderr)
        return 1
    print(
        "Backup/restore drill OK: "
        f"{result.headings} heading(s), {result.fields} evidence field(s) verified."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
