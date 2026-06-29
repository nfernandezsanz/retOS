from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def load_visual_review_gate() -> ModuleType:
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "check_visual_review.py"
    spec = importlib.util.spec_from_file_location("check_visual_review", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load visual review gate from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def template_text(gate: ModuleType) -> str:
    machine_gates = "\n".join(f"- `{item}`" for item in gate.REQUIRED_GATES)
    review_fields = "\n".join(f"- {item}:" for item in gate.REQUIRED_FIELDS)
    return f"""# Visual Review Evidence Template

Use this template for the human visual acceptance pass. Keep the completed copy with
the production promotion evidence for the release candidate.

## Candidate

{review_fields}

## Machine Evidence

Paste or link the output for each gate:

{machine_gates}

## Screenshot Evidence

{review_fields}

## Review Scope

{review_fields}

## Findings

{review_fields}

## Decision

{review_fields}
"""


def write_template(tmp_path: Path, content: str) -> Path:
    template_path = tmp_path / "visual-review-template.md"
    template_path.write_text(content, encoding="utf-8")
    return template_path


def test_visual_review_gate_accepts_required_contract(tmp_path: Path) -> None:
    gate = load_visual_review_gate()
    template_path = write_template(tmp_path, template_text(gate))

    result = gate.validate_visual_review(template_path)

    assert result.headings == len(gate.REQUIRED_HEADINGS)
    assert result.gates == len(gate.REQUIRED_GATES)
    assert result.fields == len(gate.REQUIRED_FIELDS)


def test_visual_review_gate_rejects_missing_machine_gate(tmp_path: Path) -> None:
    gate = load_visual_review_gate()
    content = template_text(gate).replace("- `make visual-audit-check`\n", "")
    template_path = write_template(tmp_path, content)

    try:
        gate.validate_visual_review(template_path)
    except gate.VisualReviewError as exc:
        assert "make visual-audit-check" in str(exc)
    else:
        raise AssertionError("Expected missing machine gate to fail")


def test_visual_review_gate_rejects_missing_review_field(tmp_path: Path) -> None:
    gate = load_visual_review_gate()
    content = template_text(gate).replace("- Visual review decision:\n", "")
    template_path = write_template(tmp_path, content)

    try:
        gate.validate_visual_review(template_path)
    except gate.VisualReviewError as exc:
        assert "Visual review decision" in str(exc)
    else:
        raise AssertionError("Expected missing review field to fail")


def test_visual_review_gate_rejects_missing_file(tmp_path: Path) -> None:
    gate = load_visual_review_gate()

    try:
        gate.validate_visual_review(tmp_path / "missing.md")
    except gate.VisualReviewError as exc:
        assert "visual review template not found" in str(exc)
    else:
        raise AssertionError("Expected missing template to fail")
