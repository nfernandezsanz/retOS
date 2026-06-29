from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType


def load_visual_gate() -> ModuleType:
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "check_visual_audit.py"
    spec = importlib.util.spec_from_file_location("check_visual_audit", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load visual audit gate from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_visual_audit(
    tmp_path: Path, *, bad_hash: bool = False, bad_viewport: bool = False
) -> Path:
    gate = load_visual_gate()
    visual_dir = tmp_path / "frontend" / "visual-audit"
    visual_dir.mkdir(parents=True)
    records = []
    for name, expected in gate.EXPECTED_SCREENSHOTS.items():
        image_path = tmp_path / "frontend" / expected["path"]
        image_path.write_bytes(f"{name}-png".encode())
        digest = gate.sha256(image_path)
        viewport = dict(expected["viewport"])
        if name == "mobile" and bad_hash:
            digest = "0" * 64
        if name == "mobile" and bad_viewport:
            viewport["width"] = 414
        records.append(
            {
                "name": name,
                "path": expected["path"],
                "sha256": digest,
                "size_bytes": image_path.stat().st_size,
                "viewport": viewport,
            }
        )
    manifest_path = visual_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "generated_by": "frontend/e2e/app.spec.ts",
                "screenshots": records,
            }
        ),
        encoding="utf-8",
    )
    return manifest_path


def test_visual_audit_gate_accepts_hash_backed_manifest(tmp_path: Path) -> None:
    gate = load_visual_gate()
    manifest_path = write_visual_audit(tmp_path)

    result = gate.validate_visual_audit(manifest_path)

    assert result.screenshots == 2
    assert result.total_size_bytes > 0


def test_visual_audit_gate_rejects_changed_hash(tmp_path: Path) -> None:
    gate = load_visual_gate()
    manifest_path = write_visual_audit(tmp_path, bad_hash=True)

    try:
        gate.validate_visual_audit(manifest_path)
    except gate.VisualAuditError as exc:
        assert "mobile screenshot sha256 changed" in str(exc)
    else:
        raise AssertionError("Expected stale screenshot hash to fail")


def test_visual_audit_gate_rejects_missing_screenshot(tmp_path: Path) -> None:
    gate = load_visual_gate()
    manifest_path = write_visual_audit(tmp_path)
    (tmp_path / "frontend" / "visual-audit" / "retos-console-mobile.png").unlink()

    try:
        gate.validate_visual_audit(manifest_path)
    except gate.VisualAuditError as exc:
        assert "mobile screenshot file not found" in str(exc)
    else:
        raise AssertionError("Expected missing screenshot to fail")


def test_visual_audit_gate_rejects_wrong_viewport(tmp_path: Path) -> None:
    gate = load_visual_gate()
    manifest_path = write_visual_audit(tmp_path, bad_viewport=True)

    try:
        gate.validate_visual_audit(manifest_path)
    except gate.VisualAuditError as exc:
        assert "mobile viewport must be" in str(exc)
    else:
        raise AssertionError("Expected wrong viewport to fail")
