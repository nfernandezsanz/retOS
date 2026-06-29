from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def load_audit_export_verifier() -> ModuleType:
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "check_audit_export.py"
    spec = importlib.util.spec_from_file_location("check_audit_export", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load audit export verifier from {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_audit_export_verifier_accepts_valid_self_test_export() -> None:
    verifier = load_audit_export_verifier()
    export = verifier.self_test_export()

    assert verifier.validate_export(export) == []


def test_audit_export_verifier_detects_payload_tampering() -> None:
    verifier = load_audit_export_verifier()
    export = verifier.self_test_export()
    export["journal_events"][0]["payload"]["status"] = "tampered"
    export["integrity"]["valid"] = False
    export["integrity"]["failures"] = [
        {
            "event_id": "event-1",
            "event_stream": "journal",
            "event_type": "job.created",
            "reason": "payload_hash_mismatch",
            "expected": "filled-by-test",
            "actual": export["integrity"]["chain"][0]["payload_hash"],
        }
    ]

    failures = verifier.integrity_failures(export)

    assert [failure["reason"] for failure in failures] == ["payload_hash_mismatch"]
    assert verifier.validate_export(export) == []


def test_audit_export_verifier_rejects_mismatched_reported_failures() -> None:
    verifier = load_audit_export_verifier()
    export = verifier.self_test_export()
    export["journal_events"][0]["payload"]["status"] = "tampered"

    errors = verifier.validate_export(export)

    assert "integrity.valid does not match recalculated failures" in errors
    assert "integrity.failures does not match recalculated failure reasons" in errors


def test_audit_export_verifier_rejects_missing_export_file_argument() -> None:
    verifier = load_audit_export_verifier()

    assert verifier.run(None, self_test=True) == 0
