from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]


def load_readme_usability_gate() -> ModuleType:
    script_path = ROOT / "scripts" / "check_readme_usability.py"
    spec = importlib.util.spec_from_file_location("check_readme_usability", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load README usability gate from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_readme(tmp_path: Path, content: str | None = None) -> Path:
    readme_path = tmp_path / "README.md"
    readme_path.write_text(
        content or (ROOT / "README.md").read_text(encoding="utf-8"), encoding="utf-8"
    )
    return readme_path


def write_makefile(tmp_path: Path, content: str | None = None) -> Path:
    makefile_path = tmp_path / "Makefile"
    makefile_path.write_text(
        content or (ROOT / "Makefile").read_text(encoding="utf-8"), encoding="utf-8"
    )
    return makefile_path


def test_readme_usability_gate_accepts_current_contract(tmp_path: Path) -> None:
    gate = load_readme_usability_gate()
    readme_path = write_readme(tmp_path)
    makefile_path = write_makefile(tmp_path)

    gate.validate_readme(readme_path, makefile_path)


def test_readme_usability_gate_tracks_frontend_format_contract() -> None:
    gate = load_readme_usability_gate()

    assert "frontend-format-check" in gate.REQUIRED_MAKE_TARGETS
    assert "make frontend-format-check" in gate.REQUIRED_PHRASES


def test_readme_usability_gate_rejects_missing_status_heading(tmp_path: Path) -> None:
    gate = load_readme_usability_gate()
    readme_path = write_readme(
        tmp_path,
        (ROOT / "README.md").read_text(encoding="utf-8").replace("## Current Status", "## Status"),
    )
    makefile_path = write_makefile(tmp_path)

    try:
        gate.validate_readme(readme_path, makefile_path)
    except SystemExit as exc:
        assert "missing heading: ## Current Status" in str(exc)
    else:
        raise AssertionError("Expected missing status heading to fail")


def test_readme_usability_gate_rejects_missing_local_action(tmp_path: Path) -> None:
    gate = load_readme_usability_gate()
    readme_path = write_readme(
        tmp_path,
        (ROOT / "README.md").read_text(encoding="utf-8").replace("make local-acceptance", ""),
    )
    makefile_path = write_makefile(tmp_path)

    try:
        gate.validate_readme(readme_path, makefile_path)
    except SystemExit as exc:
        assert "missing phrase: make local-acceptance" in str(exc)
    else:
        raise AssertionError("Expected missing local acceptance action to fail")


def test_readme_usability_gate_rejects_wrong_status_order(tmp_path: Path) -> None:
    gate = load_readme_usability_gate()
    content = (ROOT / "README.md").read_text(encoding="utf-8")
    swapped_content = (
        content.replace("## Current Status", "## __STATUS_PLACEHOLDER__", 1)
        .replace("## What You Can Do Today", "## Current Status", 1)
        .replace("## __STATUS_PLACEHOLDER__", "## What You Can Do Today", 1)
    )
    readme_path = write_readme(
        tmp_path,
        swapped_content,
    )
    makefile_path = write_makefile(tmp_path)

    try:
        gate.validate_readme(readme_path, makefile_path)
    except SystemExit as exc:
        assert "Current Status must appear before workflow details" in str(exc)
    else:
        raise AssertionError("Expected wrong status order to fail")


def test_readme_usability_gate_rejects_troubleshooting_after_audit_handoff(
    tmp_path: Path,
) -> None:
    gate = load_readme_usability_gate()
    content = (ROOT / "README.md").read_text(encoding="utf-8")
    troubleshooting_start = content.index("## Local Troubleshooting")
    audit_start = content.index("## Local Audit Handoff")
    status_start = content.index("## Current Status")
    troubleshooting = content[troubleshooting_start:audit_start]
    reordered_content = (
        content[:troubleshooting_start]
        + content[audit_start:status_start]
        + troubleshooting
        + content[status_start:]
    )
    readme_path = write_readme(tmp_path, reordered_content)
    makefile_path = write_makefile(tmp_path)

    try:
        gate.validate_readme(readme_path, makefile_path)
    except SystemExit as exc:
        assert "Local Troubleshooting must appear before Local Audit Handoff" in str(exc)
    else:
        raise AssertionError("Expected troubleshooting order drift to fail")


def test_readme_usability_gate_rejects_missing_make_target(tmp_path: Path) -> None:
    gate = load_readme_usability_gate()
    readme_path = write_readme(tmp_path)
    local_acceptance_target = (
        "\nlocal-acceptance: doctor check frontend-format-check integration frontend-test "
        "frontend-visual-audit docker-config auditor-handoff-check docker-smoke\n"
    )
    renamed_acceptance_target = (
        "\nlocal-preflight: doctor check frontend-format-check integration frontend-test "
        "frontend-visual-audit docker-config auditor-handoff-check docker-smoke\n"
    )
    makefile_content = (
        (ROOT / "Makefile")
        .read_text(encoding="utf-8")
        .replace(local_acceptance_target, renamed_acceptance_target)
    )
    makefile_path = write_makefile(tmp_path, makefile_content)

    try:
        gate.validate_readme(readme_path, makefile_path)
    except SystemExit as exc:
        assert "README command references missing Make target: local-acceptance" in str(exc)
    else:
        raise AssertionError("Expected missing Make target to fail")


def test_readme_usability_gate_rejects_missing_make_command_text(
    tmp_path: Path,
) -> None:
    gate = load_readme_usability_gate()
    readme_path = write_readme(
        tmp_path,
        (ROOT / "README.md")
        .read_text(encoding="utf-8")
        .replace("make docker-smoke", "make stack-smoke"),
    )
    makefile_path = write_makefile(tmp_path)

    try:
        gate.validate_readme(readme_path, makefile_path)
    except SystemExit as exc:
        assert "missing phrase: make docker-smoke" in str(exc)
    else:
        raise AssertionError("Expected missing README command to fail")
