import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


def load_evidence_cli() -> ModuleType:
    script_path = (
        Path(__file__).resolve().parents[1] / "scripts" / "export_eval_calibration_evidence.py"
    )
    spec = importlib.util.spec_from_file_location("export_eval_calibration_evidence", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load calibration evidence CLI from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def manifest_payload(*, passed: bool = True) -> dict[str, Any]:
    return {
        "started_at": "2026-06-28T09:05:17+00:00",
        "completed_at": "2026-06-28T09:05:18+00:00",
        "passed": passed,
        "target_count": 1,
        "max_records": 10,
        "max_cases": 5,
        "metric_gates": [{"target": "squad", "name": "retrieval_recall", "minimum": 0.8}],
        "targets": [
            {
                "key": "squad",
                "suite": "squad-v2",
                "description": "SQuAD calibration.",
                "passed": passed,
                "report_passed": passed,
                "gates_passed": passed,
                "case_count": 5,
                "metrics": {
                    "retrieval_recall": 1.0,
                    "citation_validity": 1.0,
                    "ignored_text_metric": "n/a",
                },
                "gates": [
                    {
                        "name": "retrieval_recall",
                        "target": "squad",
                        "minimum": 0.8,
                        "actual": 1.0,
                        "passed": passed,
                    }
                ],
                "dataset": {
                    "profile": "squad-dev-v2",
                    "suite": "squad",
                    "path": "../evals/datasets/squad-dev-v2-sample.json",
                    "records": 10,
                    "reused": False,
                    "source": "https://rajpurkar.github.io/SQuAD-explorer/",
                    "source_url": "https://rajpurkar.github.io/SQuAD-explorer/dataset/dev-v2.0.json",
                    "license_note": "SQuAD data is distributed by the Stanford SQuAD project.",
                },
                "reports": {
                    "json": "../evals/reports/calibration/real-squad-dev-v2.json",
                    "markdown": "../evals/reports/calibration/real-squad-dev-v2.md",
                },
            }
        ],
    }


def test_build_evidence_omits_local_paths_and_renders_markdown() -> None:
    cli = load_evidence_cli()

    evidence = cli.build_evidence(
        manifest=manifest_payload(),
        title="Alpha Calibration",
        commands=("make eval-calibration MAX_RECORDS=10 MAX_CASES=5",),
        require_passed=True,
    )
    markdown = cli.render_markdown(evidence)

    assert evidence["status"] == "PASS"
    assert evidence["targets"][0]["dataset"]["profile"] == "squad-dev-v2"
    assert "make eval-calibration MAX_RECORDS=10 MAX_CASES=5" in markdown
    assert "retrieval_recall" in markdown
    assert "https://rajpurkar.github.io/SQuAD-explorer/dataset/dev-v2.0.json" in markdown
    assert "../evals/datasets" not in markdown
    assert "../evals/reports" not in markdown


def test_build_evidence_rejects_failed_manifest_by_default() -> None:
    cli = load_evidence_cli()

    try:
        cli.build_evidence(
            manifest=manifest_payload(passed=False),
            title="Failed Calibration",
            commands=(),
            require_passed=True,
        )
    except cli.CalibrationEvidenceError as exc:
        assert "did not pass" in str(exc)
    else:
        raise AssertionError("Expected failed manifest to be rejected")

    evidence = cli.build_evidence(
        manifest=manifest_payload(passed=False),
        title="Failed Calibration",
        commands=(),
        require_passed=False,
    )
    assert evidence["status"] == "FAIL"


def test_cli_writes_evidence_file(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    cli = load_evidence_cli()
    manifest_path = tmp_path / "manifest.json"
    output_path = tmp_path / "evidence.md"
    manifest_path.write_text(json.dumps(manifest_payload()), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "export_eval_calibration_evidence.py",
            "--manifest",
            str(manifest_path),
            "--output",
            str(output_path),
            "--title",
            "CLI Evidence",
        ],
    )

    assert cli.main() == 0
    assert output_path.exists()
    assert output_path.read_text(encoding="utf-8").startswith("# CLI Evidence")


def test_build_evidence_requires_targets() -> None:
    cli = load_evidence_cli()

    try:
        cli.build_evidence(
            manifest={"passed": True, "targets": []},
            title="Empty",
            commands=(),
            require_passed=True,
        )
    except cli.CalibrationEvidenceError as exc:
        assert "at least one target" in str(exc)
    else:
        raise AssertionError("Expected empty target manifest to fail")
