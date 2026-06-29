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
        metric_gates=(cli.MetricGate(name="retrieval_recall", minimum=0.9),),
    )

    assert manifest["passed"] is True
    assert manifest["target_count"] == 2
    assert manifest["metric_gates"] == [{"name": "retrieval_recall", "minimum": 0.9}]
    assert fetch_calls == ["hotpotqa-dev-distractor"]
    assert [call["suite"] for call in build_calls] == ["hotpotqa", "hotpotqa-agent"]
    assert [call["max_cases"] for call in build_calls] == [2, 2]
    assert manifest["targets"][0]["dataset"]["reused"] is False
    assert manifest["targets"][1]["dataset"]["reused"] is True
    assert manifest["targets"][1]["dataset"]["records"] == 3
    assert (
        manifest["targets"][1]["dataset"]["source_url"]
        == cli.DATASET_PROFILES["hotpotqa-dev-distractor"].url
    )
    assert manifest["targets"][0]["report_passed"] is True
    assert manifest["targets"][0]["gates_passed"] is True
    assert manifest["targets"][0]["gates"] == [
        {
            "name": "retrieval_recall",
            "minimum": 0.9,
            "actual": 1.0,
            "passed": True,
        }
    ]
    manifest_path = Path(manifest["manifest_path"])
    assert manifest_path.exists()
    persisted = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert persisted["passed"] is True
    assert persisted["metric_gates"] == [{"name": "retrieval_recall", "minimum": 0.9}]
    assert (tmp_path / "reports" / "real-hotpotqa-dev-distractor.json").exists()
    assert (tmp_path / "reports" / "real-hotpotqa-agent-dev-distractor.md").exists()


def test_eval_calibration_reuses_existing_dataset_when_large_enough(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    cli = load_calibration_cli()
    profile = cli.DATASET_PROFILES["squad-dev-v2"]
    dataset_dir = tmp_path / "datasets"
    dataset_dir.mkdir()
    dataset_path = dataset_dir / profile.output_name
    dataset_path.write_text("[]\n", encoding="utf-8")
    metadata_path = cli.dataset_metadata_path(dataset_path)
    metadata_path.write_text(
        json.dumps(
            {
                "profile": profile.name,
                "suite": profile.suite,
                "records": 10,
                "source_url": profile.url,
                "source_path": None,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    def fail_fetch_profile(**_: object) -> dict[str, object]:
        raise AssertionError("Expected existing calibration sample to be reused")

    monkeypatch.setattr(cli, "fetch_profile", fail_fetch_profile)

    result = cli.materialize_dataset(
        profile=profile,
        output_dir=dataset_dir,
        max_records=5,
        force=False,
        download_timeout=1,
        download_retries=1,
    )

    assert result["reused"] is True
    assert result["records"] == 10


def test_eval_calibration_refetches_existing_dataset_when_too_small(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    cli = load_calibration_cli()
    profile = cli.DATASET_PROFILES["squad-dev-v2"]
    dataset_dir = tmp_path / "datasets"
    dataset_dir.mkdir()
    dataset_path = dataset_dir / profile.output_name
    dataset_path.write_text("[]\n", encoding="utf-8")
    metadata_path = cli.dataset_metadata_path(dataset_path)
    metadata_path.write_text(
        json.dumps(
            {
                "profile": profile.name,
                "suite": profile.suite,
                "records": 4,
                "source_url": profile.url,
                "source_path": None,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    fetch_calls: list[int] = []

    def fake_fetch_profile(**kwargs: object) -> dict[str, object]:
        fetch_calls.append(int(kwargs["max_records"]))
        output_dir = kwargs["output_dir"]
        assert isinstance(output_dir, Path)
        output_path = output_dir / profile.output_name
        output_path.write_text("[]\n", encoding="utf-8")
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

    monkeypatch.setattr(cli, "fetch_profile", fake_fetch_profile)

    result = cli.materialize_dataset(
        profile=profile,
        output_dir=dataset_dir,
        max_records=8,
        force=False,
        download_timeout=1,
        download_retries=1,
    )

    assert fetch_calls == [8]
    assert result["reused"] is False
    assert result["records"] == 8
    persisted_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert persisted_metadata["records"] == 8


def test_eval_calibration_refetches_existing_dataset_when_profile_drifts(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    cli = load_calibration_cli()
    profile = cli.DATASET_PROFILES["squad-dev-v2"]
    dataset_dir = tmp_path / "datasets"
    dataset_dir.mkdir()
    dataset_path = dataset_dir / profile.output_name
    dataset_path.write_text("[]\n", encoding="utf-8")
    metadata_path = cli.dataset_metadata_path(dataset_path)
    metadata_path.write_text(
        json.dumps(
            {
                "profile": "hotpotqa-dev-distractor",
                "suite": "hotpotqa",
                "records": 1000,
                "source_url": "https://example.test/wrong.json",
                "source_path": None,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    fetch_calls = 0

    def fake_fetch_profile(**kwargs: object) -> dict[str, object]:
        nonlocal fetch_calls
        fetch_calls += 1
        output_dir = kwargs["output_dir"]
        assert isinstance(output_dir, Path)
        output_path = output_dir / profile.output_name
        output_path.write_text("[]\n", encoding="utf-8")
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

    monkeypatch.setattr(cli, "fetch_profile", fake_fetch_profile)

    result = cli.materialize_dataset(
        profile=profile,
        output_dir=dataset_dir,
        max_records=8,
        force=False,
        download_timeout=1,
        download_retries=1,
    )

    assert fetch_calls == 1
    assert result["reused"] is False
    persisted_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert persisted_metadata["profile"] == profile.name
    assert persisted_metadata["suite"] == profile.suite


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


def test_eval_calibration_metric_gate_fails_manifest(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    cli = load_calibration_cli()

    def fake_fetch_profile(**kwargs: object) -> dict[str, object]:
        profile = kwargs["profile"]
        output_dir = kwargs["output_dir"]
        assert hasattr(profile, "output_name")
        assert isinstance(output_dir, Path)
        output_path = output_dir / profile.output_name
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("[]\n", encoding="utf-8")
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
        return FakeEvalReport(str(kwargs["suite"]))

    monkeypatch.setattr(cli, "fetch_profile", fake_fetch_profile)
    monkeypatch.setattr(cli, "build_report", fake_build_report)

    manifest = cli.run_calibration(
        targets=(cli.TARGETS_BY_KEY["squad"],),
        dataset_dir=tmp_path / "datasets",
        report_dir=tmp_path / "reports",
        max_records=2,
        max_cases=2,
        metric_gates=(
            cli.MetricGate(name="retrieval_recall", minimum=1.1),
            cli.MetricGate(name="missing_metric", minimum=0.1),
        ),
    )

    assert manifest["passed"] is False
    target = manifest["targets"][0]
    assert target["report_passed"] is True
    assert target["gates_passed"] is False
    assert target["passed"] is False
    assert target["gates"] == [
        {
            "name": "retrieval_recall",
            "minimum": 1.1,
            "actual": 1.0,
            "passed": False,
        },
        {
            "name": "missing_metric",
            "minimum": 0.1,
            "actual": None,
            "passed": False,
        },
    ]


def test_eval_calibration_rejects_invalid_metric_gates() -> None:
    cli = load_calibration_cli()

    for raw_gate in ("retrieval_recall", "=0.8", "retrieval_recall=not-a-number"):
        try:
            cli.parse_metric_gates((raw_gate,))
        except cli.EvalCalibrationError:
            pass
        else:
            raise AssertionError(f"Expected invalid metric gate to fail: {raw_gate}")


def test_eval_calibration_parser_accepts_repeated_metric_gates(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    cli = load_calibration_cli()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_eval_calibration.py",
            "--target",
            "squad",
            "--metric-gate",
            "retrieval_recall=0.8",
            "--metric-gate",
            "citation_validity=1.0",
        ],
    )

    args = cli.parse_args()

    assert args.metric_gate == ["retrieval_recall=0.8", "citation_validity=1.0"]
    assert cli.parse_metric_gates(args.metric_gate) == (
        cli.MetricGate(name="retrieval_recall", minimum=0.8),
        cli.MetricGate(name="citation_validity", minimum=1.0),
    )


def test_eval_calibration_scoped_metric_gates_apply_to_matching_target(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    cli = load_calibration_cli()

    def fake_fetch_profile(**kwargs: object) -> dict[str, object]:
        profile = kwargs["profile"]
        output_dir = kwargs["output_dir"]
        assert hasattr(profile, "output_name")
        assert isinstance(output_dir, Path)
        output_path = output_dir / profile.output_name
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("[]\n", encoding="utf-8")
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
        return FakeEvalReport(str(kwargs["suite"]))

    monkeypatch.setattr(cli, "fetch_profile", fake_fetch_profile)
    monkeypatch.setattr(cli, "build_report", fake_build_report)

    metric_gates = cli.parse_metric_gates(
        (
            "squad.retrieval_recall=0.9",
            "hotpotqa-agent.query_plan=0.9",
        )
    )
    manifest = cli.run_calibration(
        targets=(cli.TARGETS_BY_KEY["squad"], cli.TARGETS_BY_KEY["hotpotqa-agent"]),
        dataset_dir=tmp_path / "datasets",
        report_dir=tmp_path / "reports",
        max_records=2,
        max_cases=2,
        metric_gates=metric_gates,
    )

    assert manifest["metric_gates"] == [
        {"name": "retrieval_recall", "minimum": 0.9, "target": "squad"},
        {"name": "query_plan", "minimum": 0.9, "target": "hotpotqa-agent"},
    ]
    assert manifest["targets"][0]["gates"] == [
        {
            "name": "retrieval_recall",
            "minimum": 0.9,
            "target": "squad",
            "actual": 1.0,
            "passed": True,
        }
    ]
    assert manifest["targets"][1]["gates"] == [
        {
            "name": "query_plan",
            "minimum": 0.9,
            "target": "hotpotqa-agent",
            "actual": None,
            "passed": False,
        }
    ]
