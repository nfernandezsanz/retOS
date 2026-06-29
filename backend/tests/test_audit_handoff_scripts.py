from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def load_audit_bundle_gate() -> ModuleType:
    script_path = ROOT / "scripts" / "check_audit_bundle.py"
    scripts_path = str(ROOT / "scripts")
    if scripts_path not in sys.path:
        sys.path.insert(0, scripts_path)
    spec = importlib.util.spec_from_file_location("check_audit_bundle", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load audit bundle gate from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run_script(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [sys.executable, script],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def bundle_manifest_fixture(gate: ModuleType) -> dict[str, Any]:
    return {
        "visual_audit": {
            "local_manifest": {
                "exists": True,
                "json": {
                    "coverage": {
                        "sections": gate.EXPECTED_VISUAL_SECTIONS,
                        "visible_sections": gate.EXPECTED_VISUAL_SECTIONS,
                        "modules": gate.EXPECTED_VISUAL_MODULES,
                        "tooltip_targets": gate.MIN_VISUAL_TOOLTIP_TARGETS,
                        "no_horizontal_overflow": True,
                        "responsive_checks": [
                            {
                                "width": width,
                                "height": 900,
                                "no_horizontal_overflow": True,
                            }
                            for width in gate.EXPECTED_VISUAL_RESPONSIVE_WIDTHS
                        ],
                    }
                },
            }
        }
    }


def test_audit_bundle_gate_accepts_bundled_visual_coverage() -> None:
    gate = load_audit_bundle_gate()

    gate.validate_visual_bundle_evidence(
        bundle_manifest_fixture(gate),
        (
            "Visual coverage: ready - 6 section(s), 14 module(s), "
            "23 tooltip target(s), no-overflow widths: 375, 768, 1024, 1440"
        ),
        visual_manifest_bundled=True,
    )


def test_audit_bundle_gate_rejects_missing_visual_breakpoint() -> None:
    gate = load_audit_bundle_gate()
    manifest = bundle_manifest_fixture(gate)
    coverage = manifest["visual_audit"]["local_manifest"]["json"]["coverage"]
    responsive_checks = coverage["responsive_checks"]
    coverage["responsive_checks"] = responsive_checks[:-1]

    try:
        gate.validate_visual_bundle_evidence(
            manifest,
            (
                "Visual coverage: ready - 6 section(s), 14 module(s), "
                "23 tooltip target(s), no-overflow widths: 375, 768, 1024, 1440"
            ),
            visual_manifest_bundled=True,
        )
    except SystemExit as exc:
        assert "bundled visual coverage missing responsive width" in str(exc)
    else:
        raise AssertionError("Expected missing visual breakpoint to fail")


def test_audit_handoff_report_check_runs_offline() -> None:
    result = run_script("scripts/check_audit_handoff_report.py")

    assert result.returncode == 0, result.stderr
    assert "Audit handoff report OK" in result.stdout


def test_audit_bundle_check_runs_offline() -> None:
    result = run_script("scripts/check_audit_bundle.py")

    assert result.returncode == 0, result.stderr
    assert "Audit bundle OK" in result.stdout
