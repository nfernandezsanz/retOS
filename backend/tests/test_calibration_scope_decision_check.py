from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def load_calibration_scope_decision_gate() -> ModuleType:
    script_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "check_calibration_scope_decision.py"
    )
    spec = importlib.util.spec_from_file_location("check_calibration_scope_decision", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load calibration scope decision gate from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def template_text(gate: ModuleType) -> str:
    fields = "\n".join(f"- {item}:" for item in gate.REQUIRED_FIELDS)
    return f"""# Calibration Scope Decision Evidence Template

Use this template when a release candidate relies on bounded public calibration slices or
when broader public-slice trend evidence is attached. Keep the completed copy with the
production promotion evidence for the release candidate.

## Candidate

{fields}

## Versioned Evidence

{fields}

## Pilot Scope Acceptance

{fields}

## Broader Trend Evidence

{fields}

## Risk Decision

{fields}
"""


def write_template(tmp_path: Path, content: str) -> Path:
    template_path = tmp_path / "calibration-scope-decision-template.md"
    template_path.write_text(content, encoding="utf-8")
    return template_path


def test_calibration_scope_decision_gate_accepts_required_contract(
    tmp_path: Path,
) -> None:
    gate = load_calibration_scope_decision_gate()
    template_path = write_template(tmp_path, template_text(gate))

    result = gate.validate_calibration_scope_decision(template_path)

    assert result.headings == len(gate.REQUIRED_HEADINGS)
    assert result.fields == len(gate.REQUIRED_FIELDS)


def test_calibration_scope_decision_gate_rejects_missing_pilot_field(
    tmp_path: Path,
) -> None:
    gate = load_calibration_scope_decision_gate()
    content = template_text(gate).replace("- Pilot user group:\n", "")
    template_path = write_template(tmp_path, content)

    try:
        gate.validate_calibration_scope_decision(template_path)
    except gate.CalibrationScopeDecisionError as exc:
        assert "Pilot user group" in str(exc)
    else:
        raise AssertionError("Expected missing pilot field to fail")


def test_calibration_scope_decision_gate_rejects_missing_heading(
    tmp_path: Path,
) -> None:
    gate = load_calibration_scope_decision_gate()
    content = template_text(gate).replace("## Broader Trend Evidence\n\n", "")
    template_path = write_template(tmp_path, content)

    try:
        gate.validate_calibration_scope_decision(template_path)
    except gate.CalibrationScopeDecisionError as exc:
        assert "## Broader Trend Evidence" in str(exc)
    else:
        raise AssertionError("Expected missing heading to fail")


def test_calibration_scope_decision_gate_rejects_missing_file(tmp_path: Path) -> None:
    gate = load_calibration_scope_decision_gate()

    try:
        gate.validate_calibration_scope_decision(tmp_path / "missing.md")
    except gate.CalibrationScopeDecisionError as exc:
        assert "calibration scope decision template not found" in str(exc)
    else:
        raise AssertionError("Expected missing template to fail")
