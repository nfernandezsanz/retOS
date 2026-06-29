from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def load_target_security_review_gate() -> ModuleType:
    script_path = (
        Path(__file__).resolve().parents[2] / "scripts" / "check_target_security_review.py"
    )
    spec = importlib.util.spec_from_file_location("check_target_security_review", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load target security review gate from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def template_text(gate: ModuleType) -> str:
    fields = "\n".join(f"- {item}:" for item in gate.REQUIRED_FIELDS)
    return f"""# Target Security Review Evidence Template

Use this template for the target-environment security review. Keep the completed copy
with the production promotion evidence for the release candidate.

## Candidate

{fields}

## Auth And Access

{fields}

## Secrets And Provider Keys

{fields}

## Network And Runtime Exposure

{fields}

## Data Handling And Audit

{fields}

## Release Provenance

{fields}

## Operations And Rollback

{fields}

## Decision

{fields}
"""


def write_template(tmp_path: Path, content: str) -> Path:
    template_path = tmp_path / "target-security-review-template.md"
    template_path.write_text(content, encoding="utf-8")
    return template_path


def test_target_security_review_gate_accepts_required_contract(tmp_path: Path) -> None:
    gate = load_target_security_review_gate()
    template_path = write_template(tmp_path, template_text(gate))

    result = gate.validate_target_security_review(template_path)

    assert result.headings == len(gate.REQUIRED_HEADINGS)
    assert result.fields == len(gate.REQUIRED_FIELDS)


def test_target_security_review_gate_rejects_missing_network_field(
    tmp_path: Path,
) -> None:
    gate = load_target_security_review_gate()
    content = template_text(gate).replace("- CORS origins reviewed:\n", "")
    template_path = write_template(tmp_path, content)

    try:
        gate.validate_target_security_review(template_path)
    except gate.TargetSecurityReviewError as exc:
        assert "CORS origins reviewed" in str(exc)
    else:
        raise AssertionError("Expected missing network field to fail")


def test_target_security_review_gate_rejects_missing_heading(tmp_path: Path) -> None:
    gate = load_target_security_review_gate()
    content = template_text(gate).replace("## Data Handling And Audit\n\n", "")
    template_path = write_template(tmp_path, content)

    try:
        gate.validate_target_security_review(template_path)
    except gate.TargetSecurityReviewError as exc:
        assert "## Data Handling And Audit" in str(exc)
    else:
        raise AssertionError("Expected missing heading to fail")


def test_target_security_review_gate_rejects_missing_file(tmp_path: Path) -> None:
    gate = load_target_security_review_gate()

    try:
        gate.validate_target_security_review(tmp_path / "missing.md")
    except gate.TargetSecurityReviewError as exc:
        assert "target security review template not found" in str(exc)
    else:
        raise AssertionError("Expected missing template to fail")
