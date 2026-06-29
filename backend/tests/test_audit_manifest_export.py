import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType


def load_audit_manifest_exporter() -> ModuleType:
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "export_audit_manifest.py"
    spec = importlib.util.spec_from_file_location("export_audit_manifest", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load audit manifest exporter from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_coverage_targets_read_makefile_and_coverage_json(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    exporter = load_audit_manifest_exporter()
    coverage_path = tmp_path / "backend" / "coverage.json"
    coverage_path.parent.mkdir()
    coverage_path.write_text(
        json.dumps(
            {
                "meta": {"branch_coverage": True},
                "totals": {
                    "covered_branches": 1262,
                    "num_branches": 1394,
                    "percent_branches_covered": 90.53084648493544,
                    "percent_covered": 95.24985068684054,
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "Makefile").write_text("BRANCH_COVERAGE_MIN ?= 90.53\n", encoding="utf-8")
    monkeypatch.setattr(exporter, "ROOT", tmp_path)

    targets = exporter.coverage_targets()

    assert targets["branch_minimum_percent"] == 90.53
    assert targets["last_recorded_branch_percent"] == 90.53
    assert targets["last_recorded_total_percent"] == 95.25
    assert targets["covered_branches"] == 1262
    assert targets["num_branches"] == 1394
    assert targets["branch_coverage_enabled"] is True
    assert targets["source"] == "coverage.py json"
    assert targets["source_available"] is True
    assert targets["source_path"] == "backend/coverage.json"


def test_coverage_targets_report_missing_coverage_json(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    exporter = load_audit_manifest_exporter()
    (tmp_path / "Makefile").write_text("BRANCH_COVERAGE_MIN ?= 91.25\n", encoding="utf-8")
    monkeypatch.setattr(exporter, "ROOT", tmp_path)

    targets = exporter.coverage_targets()

    assert targets["branch_minimum_percent"] == 91.25
    assert targets["last_recorded_branch_percent"] == 0.0
    assert targets["last_recorded_total_percent"] == 0.0
    assert targets["source"] == "fallback"
    assert targets["source_available"] is False
    assert targets["source_reason"] == "coverage report not found"


def test_coverage_targets_report_unparseable_coverage_json(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    exporter = load_audit_manifest_exporter()
    coverage_path = tmp_path / "backend" / "coverage.json"
    coverage_path.parent.mkdir()
    coverage_path.write_text('{"totals": {}}', encoding="utf-8")
    (tmp_path / "Makefile").write_text("BRANCH_COVERAGE_MIN ?= 90.53\n", encoding="utf-8")
    monkeypatch.setattr(exporter, "ROOT", tmp_path)

    targets = exporter.coverage_targets()

    assert targets["branch_minimum_percent"] == 90.53
    assert targets["source_available"] is False
    assert targets["source_reason"].startswith("coverage report could not be parsed:")


def test_manifest_exporter_hashes_release_evidence_files() -> None:
    exporter = load_audit_manifest_exporter()

    for path in (
        "docs/releases/evidence/2026.06.28-alpha.1-calibration.md",
        "docs/releases/evidence/2026.06.28-alpha.1-calibration-trend.md",
        "docs/releases/evidence/production-promotion-template.md",
    ):
        assert path in exporter.CRITICAL_FILES
