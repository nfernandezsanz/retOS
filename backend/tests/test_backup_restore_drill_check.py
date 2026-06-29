from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def load_backup_restore_drill_gate() -> ModuleType:
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "check_backup_restore_drill.py"
    spec = importlib.util.spec_from_file_location("check_backup_restore_drill", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load backup/restore drill gate from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def template_text(gate: ModuleType) -> str:
    fields = "\n".join(f"- {item}:" for item in gate.REQUIRED_FIELDS)
    return f"""# Backup And Restore Drill Evidence Template

Use this template for a local or target-environment backup/restore rehearsal. Keep the
completed copy with the production promotion evidence for the release candidate.

## Candidate

{fields}

## Backup Evidence

{fields}

## Restore Evidence

{fields}

## Health Evidence

{fields}

## Audit Evidence

{fields}

## Decision

{fields}
"""


def write_template(tmp_path: Path, content: str) -> Path:
    template_path = tmp_path / "backup-restore-drill-template.md"
    template_path.write_text(content, encoding="utf-8")
    return template_path


def test_backup_restore_drill_gate_accepts_required_contract(tmp_path: Path) -> None:
    gate = load_backup_restore_drill_gate()
    template_path = write_template(tmp_path, template_text(gate))

    result = gate.validate_backup_restore_drill(template_path)

    assert result.headings == len(gate.REQUIRED_HEADINGS)
    assert result.fields == len(gate.REQUIRED_FIELDS)


def test_backup_restore_drill_gate_rejects_missing_health_field(tmp_path: Path) -> None:
    gate = load_backup_restore_drill_gate()
    content = template_text(gate).replace("- `make api-smoke` output:\n", "")
    template_path = write_template(tmp_path, content)

    try:
        gate.validate_backup_restore_drill(template_path)
    except gate.BackupRestoreDrillError as exc:
        assert "`make api-smoke` output" in str(exc)
    else:
        raise AssertionError("Expected missing health field to fail")


def test_backup_restore_drill_gate_rejects_missing_heading(tmp_path: Path) -> None:
    gate = load_backup_restore_drill_gate()
    content = template_text(gate).replace("## Audit Evidence\n\n", "")
    template_path = write_template(tmp_path, content)

    try:
        gate.validate_backup_restore_drill(template_path)
    except gate.BackupRestoreDrillError as exc:
        assert "## Audit Evidence" in str(exc)
    else:
        raise AssertionError("Expected missing heading to fail")


def test_backup_restore_drill_gate_rejects_missing_file(tmp_path: Path) -> None:
    gate = load_backup_restore_drill_gate()

    try:
        gate.validate_backup_restore_drill(tmp_path / "missing.md")
    except gate.BackupRestoreDrillError as exc:
        assert "backup/restore drill template not found" in str(exc)
    else:
        raise AssertionError("Expected missing template to fail")
