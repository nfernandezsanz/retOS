import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


def load_calibration_cli() -> ModuleType:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_eval_calibration.py"
    scripts_dir = str(script_path.parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    spec = importlib.util.spec_from_file_location("run_eval_calibration", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load eval calibration CLI from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeEvalReport:
    def __init__(self, suite_name: str, *, passed: bool = True) -> None:
        self.suite_name = suite_name
        self.passed = passed

    def to_dict(self) -> dict[str, object]:
        return {
            "suite_name": self.suite_name,
            "passed": self.passed,
            "case_count": 2,
            "metadata": {"source": "test"},
            "metrics": {
                "retrieval_recall": 1.0,
                "citation_validity": 1.0,
                "grounded_answer": 1.0,
                "abstention": 1.0,
                "budget_compliance": 1.0,
            },
            "cases": [],
        }

    def to_markdown(self) -> str:
        return f"# Eval Report: {self.suite_name}\n\nStatus: PASS\n"


def test_eval_calibration_reuses_shared_dataset_and_writes_manifest(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    cli = load_calibration_cli()
    fetch_calls: list[str] = []
    build_calls: list[dict[str, Any]] = []

    def fake_fetch_profile(**kwargs: object) -> dict[str, object]:
        profile = kwargs["profile"]
        output_dir = kwargs["output_dir"]
        assert hasattr(profile, "output_name")
        assert isinstance(output_dir, Path)
        output_path = output_dir / profile.output_name
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("[]\n", encoding="utf-8")
        fetch_calls.append(profile.name)
        return {
            "profile": profile.name,
            "suite": profile.suite,
            "path": str(output_path),
            "records": kwargs["max_records"],
            "source": profile.source_homepage,
            "source_url": profile.url,
            "source_path": None,
            "license_note": profile.license_note,
        }

    def fake_build_report(**kwargs: object) -> FakeEvalReport:
        build_calls.append(dict(kwargs))
        return FakeEvalReport(str(kwargs["suite"]))

    monkeypatch.setattr(cli, "fetch_profile", fake_fetch_profile)
    monkeypatch.setattr(cli, "build_report", fake_build_report)

    manifest = cli.run_calibration(
        targets=(cli.TARGETS_BY_KEY["hotpotqa"], cli.TARGETS_BY_KEY["hotpotqa-agent"]),
        dataset_dir=tmp_path / "datasets",
        report_dir=tmp_path / "reports",
        max_records=3,
        max_cases=2,
    )

    assert manifest["passed"] is True
    assert manifest["target_count"] == 2
    assert fetch_calls == ["hotpotqa-dev-distractor"]
    assert [call["suite"] for call in build_calls] == ["hotpotqa", "hotpotqa-agent"]
    assert [call["max_cases"] for call in build_calls] == [2, 2]
    assert manifest["targets"][0]["dataset"]["reused"] is False
    assert manifest["targets"][1]["dataset"]["reused"] is True
    manifest_path = Path(manifest["manifest_path"])
    assert manifest_path.exists()
    persisted = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert persisted["passed"] is True
    assert (tmp_path / "reports" / "real-hotpotqa-dev-distractor.json").exists()
    assert (tmp_path / "reports" / "real-hotpotqa-agent-dev-distractor.md").exists()


def test_eval_calibration_rejects_invalid_limits(tmp_path: Path) -> None:
    cli = load_calibration_cli()

    try:
        cli.run_calibration(
            targets=(cli.TARGETS_BY_KEY["squad"],),
            dataset_dir=tmp_path / "datasets",
            report_dir=tmp_path / "reports",
            max_records=0,
            max_cases=None,
        )
    except cli.EvalCalibrationError as exc:
        assert "--max-records" in str(exc)
    else:
        raise AssertionError("Expected invalid max_records to fail")

    try:
        cli.run_calibration(
            targets=(),
            dataset_dir=tmp_path / "datasets",
            report_dir=tmp_path / "reports",
            max_records=1,
            max_cases=None,
        )
    except cli.EvalCalibrationError as exc:
        assert "At least one" in str(exc)
    else:
        raise AssertionError("Expected empty targets to fail")
