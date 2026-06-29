from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def load_audit_manifest_gate() -> ModuleType:
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "check_audit_manifest.py"
    spec = importlib.util.spec_from_file_location("check_audit_manifest", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load audit manifest gate from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def visual_manifest_fixture(gate: ModuleType) -> dict[str, object]:
    return {
        "coverage": {
            "sections": gate.EXPECTED_VISUAL_SECTIONS,
            "visible_sections": gate.EXPECTED_VISUAL_SECTIONS,
            "modules": gate.EXPECTED_VISUAL_MODULES,
            "tooltip_targets": gate.MIN_VISUAL_TOOLTIP_TARGETS,
            "no_horizontal_overflow": True,
            "responsive_checks": [
                {"width": width, "height": 900, "no_horizontal_overflow": True}
                for width in gate.EXPECTED_VISUAL_RESPONSIVE_WIDTHS
            ],
        },
        "screenshots": [
            {
                "name": "desktop",
                "path": "visual-audit/retos-console-desktop.png",
                "sha256": "a" * 64,
                "size_bytes": 1024,
                "viewport": {"width": 1440, "height": 900},
            },
            {
                "name": "mobile",
                "path": "visual-audit/retos-console-mobile.png",
                "sha256": "b" * 64,
                "size_bytes": 512,
                "viewport": {"width": 390, "height": 844},
            },
        ],
    }


def test_audit_manifest_gate_accepts_visual_coverage_metadata() -> None:
    gate = load_audit_manifest_gate()

    gate.validate_visual_manifest_json(visual_manifest_fixture(gate))


def test_audit_manifest_gate_rejects_missing_visual_coverage() -> None:
    gate = load_audit_manifest_gate()
    manifest = visual_manifest_fixture(gate)
    manifest.pop("coverage")

    try:
        gate.validate_visual_manifest_json(manifest)
    except SystemExit as exc:
        assert "visual audit manifest must include coverage" in str(exc)
    else:
        raise AssertionError("Expected missing visual coverage to fail")


def test_audit_manifest_gate_rejects_missing_visual_breakpoint() -> None:
    gate = load_audit_manifest_gate()
    manifest = visual_manifest_fixture(gate)
    coverage = manifest["coverage"]
    assert isinstance(coverage, dict)
    responsive_checks = coverage["responsive_checks"]
    assert isinstance(responsive_checks, list)
    coverage["responsive_checks"] = responsive_checks[:-1]

    try:
        gate.validate_visual_manifest_json(manifest)
    except SystemExit as exc:
        assert "visual audit coverage missing responsive width" in str(exc)
    else:
        raise AssertionError("Expected missing visual breakpoint to fail")


def test_audit_manifest_gate_requires_release_evidence_hashes() -> None:
    gate = load_audit_manifest_gate()

    for path in (
        "docs/releases/evidence/2026.06.28-alpha.1-calibration.md",
        "docs/releases/evidence/2026.06.28-alpha.1-calibration-trend.md",
        "docs/releases/evidence/production-promotion-template.md",
    ):
        assert path in gate.REQUIRED_CRITICAL_FILES
