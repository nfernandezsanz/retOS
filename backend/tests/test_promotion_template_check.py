from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def load_promotion_template_gate() -> ModuleType:
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "check_promotion_template.py"
    spec = importlib.util.spec_from_file_location("check_promotion_template", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load promotion template gate from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def template_text(gate: ModuleType) -> str:
    machine_gates = "\n".join(f"- `{item}`" for item in gate.REQUIRED_MACHINE_GATES)
    review_fields = "\n".join(f"- {item}:" for item in gate.REQUIRED_FIELDS)
    return f"""# Production Promotion Evidence Template

Use this template for the human promotion review. Keep the completed copy with the
versioned release note or the release record for the target environment.

## Candidate

{review_fields}

## Machine Evidence

Paste or link the output for each gate:

{machine_gates}

## Release Provenance

{review_fields}

## Visual Review

{review_fields}

## Backup And Restore Rehearsal

{review_fields}

## Security Review

{review_fields}

## Rollback

{review_fields}

## Decision

{review_fields}
"""


def write_template(tmp_path: Path, content: str) -> Path:
    template_path = tmp_path / "production-promotion-template.md"
    template_path.write_text(content, encoding="utf-8")
    return template_path


def test_promotion_template_gate_accepts_required_contract(tmp_path: Path) -> None:
    gate = load_promotion_template_gate()
    template_path = write_template(tmp_path, template_text(gate))

    result = gate.validate_promotion_template(template_path)

    assert result.headings == len(gate.REQUIRED_HEADINGS)
    assert result.gates == len(gate.REQUIRED_MACHINE_GATES)
    assert result.fields == len(gate.REQUIRED_FIELDS)


def test_promotion_template_gate_rejects_missing_machine_gate(tmp_path: Path) -> None:
    gate = load_promotion_template_gate()
    content = template_text(gate).replace("- `make local-acceptance`\n", "")
    template_path = write_template(tmp_path, content)

    try:
        gate.validate_promotion_template(template_path)
    except gate.PromotionTemplateError as exc:
        assert "make local-acceptance" in str(exc)
    else:
        raise AssertionError("Expected missing machine gate to fail")


def test_promotion_template_gate_rejects_missing_review_field(tmp_path: Path) -> None:
    gate = load_promotion_template_gate()
    content = template_text(gate).replace("- Promotion decision:\n", "")
    template_path = write_template(tmp_path, content)

    try:
        gate.validate_promotion_template(template_path)
    except gate.PromotionTemplateError as exc:
        assert "Promotion decision" in str(exc)
    else:
        raise AssertionError("Expected missing review field to fail")


def test_promotion_template_gate_rejects_missing_file(tmp_path: Path) -> None:
    gate = load_promotion_template_gate()

    try:
        gate.validate_promotion_template(tmp_path / "missing.md")
    except gate.PromotionTemplateError as exc:
        assert "promotion template not found" in str(exc)
    else:
        raise AssertionError("Expected missing template to fail")
