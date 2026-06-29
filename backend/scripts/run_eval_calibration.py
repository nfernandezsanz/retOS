from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fetch_eval_dataset import DATASET_PROFILES, DatasetFetchError, DatasetProfile, fetch_profile
from retos.evals.reports import write_report_files
from run_eval_smoke import build_report


class EvalCalibrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class CalibrationTarget:
    key: str
    profile_name: str
    suite: str
    report_stem: str
    description: str


DEFAULT_TARGETS: tuple[CalibrationTarget, ...] = (
    CalibrationTarget(
        key="squad",
        profile_name="squad-dev-v2",
        suite="squad",
        report_stem="real-squad-dev-v2",
        description="SQuAD 2.0 answerable/unanswerable retrieval calibration.",
    ),
    CalibrationTarget(
        key="hotpotqa",
        profile_name="hotpotqa-dev-distractor",
        suite="hotpotqa",
        report_stem="real-hotpotqa-dev-distractor",
        description="HotpotQA multi-hop retrieval calibration.",
    ),
    CalibrationTarget(
        key="hotpotqa-agent",
        profile_name="hotpotqa-dev-distractor",
        suite="hotpotqa-agent",
        report_stem="real-hotpotqa-agent-dev-distractor",
        description="HotpotQA supporting facts through the agent audit harness.",
    ),
    CalibrationTarget(
        key="natural-questions",
        profile_name="nq-open-train-adapter",
        suite="natural-questions",
        report_stem="real-nq-open-train-adapter",
        description="NQ-Open questions converted into the RetOS Natural Questions adapter.",
    ),
)

TARGETS_BY_KEY = {target.key: target for target in DEFAULT_TARGETS}


@dataclass(frozen=True)
class MetricGate:
    name: str
    minimum: float
    target: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch bounded public dataset samples and run RetOS real-dataset "
            "calibration reports. This is opt-in and never used by default CI."
        )
    )
    parser.add_argument(
        "--target",
        action="append",
        choices=tuple(TARGETS_BY_KEY),
        help="Calibration target to run. May be repeated. Defaults to all public targets.",
    )
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=Path("evals/datasets"),
        help="Directory for bounded dataset samples.",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path("evals/reports/calibration"),
        help="Directory for per-target JSON/Markdown reports and manifest.json.",
    )
    parser.add_argument(
        "--max-records",
        type=int,
        default=100,
        help="Maximum records or QA cases to fetch per dataset profile.",
    )
    parser.add_argument(
        "--max-cases",
        type=int,
        default=None,
        help="Maximum cases to evaluate per target. Defaults to --max-records.",
    )
    parser.add_argument(
        "--force-datasets",
        action="store_true",
        help="Overwrite existing sampled dataset files instead of reusing them.",
    )
    parser.add_argument(
        "--download-timeout",
        type=float,
        default=60.0,
        help="Per-attempt dataset download timeout in seconds.",
    )
    parser.add_argument(
        "--download-retries",
        type=int,
        default=2,
        help="Attempts per source URL before trying the next mirror.",
    )
    parser.add_argument(
        "--metric-gate",
        action="append",
        metavar="NAME=MINIMUM",
        help=(
            "Require every target to report metric NAME at or above MINIMUM. "
            "May be repeated for release promotion gates."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    targets = tuple(TARGETS_BY_KEY[key] for key in args.target) if args.target else DEFAULT_TARGETS
    try:
        manifest = run_calibration(
            targets=targets,
            dataset_dir=args.dataset_dir,
            report_dir=args.report_dir,
            max_records=args.max_records,
            max_cases=args.max_cases,
            force_datasets=args.force_datasets,
            download_timeout=args.download_timeout,
            download_retries=args.download_retries,
            metric_gates=parse_metric_gates(args.metric_gate or ()),
        )
    except (DatasetFetchError, EvalCalibrationError) as exc:
        print(f"Eval calibration error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if manifest["passed"] else 1


def run_calibration(
    *,
    targets: tuple[CalibrationTarget, ...],
    dataset_dir: Path,
    report_dir: Path,
    max_records: int,
    max_cases: int | None,
    force_datasets: bool = False,
    download_timeout: float = 60.0,
    download_retries: int = 2,
    metric_gates: tuple[MetricGate, ...] = (),
) -> dict[str, Any]:
    if not targets:
        raise EvalCalibrationError("At least one calibration target is required")
    if max_records < 1:
        raise EvalCalibrationError("--max-records must be greater than zero")
    if max_cases is not None and max_cases < 1:
        raise EvalCalibrationError("--max-cases must be greater than zero")
    case_limit = max_cases if max_cases is not None else max_records
    report_dir.mkdir(parents=True, exist_ok=True)

    started_at = datetime.now(UTC).isoformat()
    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="retos-eval-calibration-") as temp_dir:
        index_root = Path(temp_dir)
        for target in targets:
            result = run_target(
                target=target,
                dataset_dir=dataset_dir,
                report_dir=report_dir,
                index_root=index_root / target.key,
                max_records=max_records,
                max_cases=case_limit,
                force_dataset=force_datasets,
                download_timeout=download_timeout,
                download_retries=download_retries,
                metric_gates=metric_gates,
            )
            results.append(result)

    manifest = {
        "started_at": started_at,
        "completed_at": datetime.now(UTC).isoformat(),
        "passed": all(result["passed"] for result in results),
        "target_count": len(results),
        "max_records": max_records,
        "max_cases": case_limit,
        "metric_gates": [metric_gate_payload(gate) for gate in metric_gates],
        "targets": results,
    }
    manifest_path = report_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest["manifest_path"] = str(manifest_path)
    return manifest


def run_target(
    *,
    target: CalibrationTarget,
    dataset_dir: Path,
    report_dir: Path,
    index_root: Path,
    max_records: int,
    max_cases: int,
    force_dataset: bool,
    download_timeout: float,
    download_retries: int,
    metric_gates: tuple[MetricGate, ...],
) -> dict[str, Any]:
    profile = DATASET_PROFILES[target.profile_name]
    dataset_result = materialize_dataset(
        profile=profile,
        output_dir=dataset_dir,
        max_records=max_records,
        force=force_dataset,
        download_timeout=download_timeout,
        download_retries=download_retries,
    )
    dataset_path = Path(str(dataset_result["path"]))
    report = build_report(
        index_root=index_root,
        suite=target.suite,
        dataset_path=dataset_path,
        max_cases=max_cases,
        dataset_format="manifest",
    )
    json_path, markdown_path = write_report_files(
        report=report,
        report_dir=report_dir,
        report_stem=target.report_stem,
    )
    report_payload = report.to_dict()
    gate_results = evaluate_metric_gates(
        target_key=target.key,
        metrics=report_payload["metrics"],
        metric_gates=metric_gates,
    )
    gates_passed = all(gate["passed"] for gate in gate_results)
    return {
        "key": target.key,
        "suite": report.suite_name,
        "description": target.description,
        "passed": report.passed and gates_passed,
        "report_passed": report.passed,
        "gates_passed": gates_passed,
        "gates": gate_results,
        "case_count": report_payload["case_count"],
        "metrics": report_payload["metrics"],
        "dataset": dataset_result,
        "reports": {
            "json": str(json_path),
            "markdown": str(markdown_path),
        },
    }


def materialize_dataset(
    *,
    profile: DatasetProfile,
    output_dir: Path,
    max_records: int,
    force: bool,
    download_timeout: float,
    download_retries: int,
) -> dict[str, Any]:
    output_path = output_dir / profile.output_name
    metadata_path = dataset_metadata_path(output_path)
    if output_path.exists() and not force:
        metadata = read_dataset_metadata(metadata_path)
        records = metadata.get("records")
        if (
            type(records) is int
            and records >= max_records
            and metadata.get("profile") == profile.name
            and metadata.get("suite") == profile.suite
        ):
            return {
                "profile": profile.name,
                "suite": profile.suite,
                "path": str(output_path),
                "records": records,
                "source": profile.source_homepage,
                "source_url": metadata.get("source_url"),
                "source_path": metadata.get("source_path"),
                "license_note": profile.license_note,
                "reused": True,
            }
    result = fetch_profile(
        profile=profile,
        output_dir=output_dir,
        max_records=max_records,
        force=force,
        download_timeout=download_timeout,
        download_retries=download_retries,
    )
    write_dataset_metadata(metadata_path, result)
    return {**result, "reused": False}


def dataset_metadata_path(dataset_path: Path) -> Path:
    return dataset_path.with_name(f"{dataset_path.name}.metadata.json")


def read_dataset_metadata(metadata_path: Path) -> dict[str, Any]:
    if not metadata_path.is_file():
        return {}
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EvalCalibrationError(f"Dataset metadata is not valid JSON: {metadata_path}") from exc
    if not isinstance(payload, dict):
        raise EvalCalibrationError(f"Dataset metadata root must be an object: {metadata_path}")
    return payload


def write_dataset_metadata(metadata_path: Path, result: dict[str, object]) -> None:
    metadata = {key: value for key, value in result.items() if key != "path"}
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def parse_metric_gates(raw_gates: tuple[str, ...] | list[str]) -> tuple[MetricGate, ...]:
    gates: list[MetricGate] = []
    for raw_gate in raw_gates:
        raw_name, separator, raw_minimum = raw_gate.partition("=")
        raw_name = raw_name.strip()
        raw_minimum = raw_minimum.strip()
        if separator != "=" or not raw_name or not raw_minimum:
            raise EvalCalibrationError(
                "--metric-gate must use NAME=MINIMUM or TARGET.NAME=MINIMUM, "
                "for example retrieval_recall=0.80 or hotpotqa.retrieval_recall=0.80"
            )
        raw_target, dot, name = raw_name.partition(".")
        target = raw_target.strip() if dot else None
        name = name.strip() if dot else raw_name
        if not name or target == "":
            raise EvalCalibrationError(
                "--metric-gate must include a metric name after the optional target scope"
            )
        try:
            minimum = float(raw_minimum)
        except ValueError as exc:
            raise EvalCalibrationError(
                f"--metric-gate minimum for {name!r} must be numeric"
            ) from exc
        gates.append(MetricGate(name=name, minimum=minimum, target=target))
    return tuple(gates)


def evaluate_metric_gates(
    *,
    target_key: str,
    metrics: dict[str, Any],
    metric_gates: tuple[MetricGate, ...],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for gate in metric_gates:
        if gate.target is not None and gate.target != target_key:
            continue
        value = metrics.get(gate.name)
        numeric_value = value if isinstance(value, int | float) else None
        gate_payload = metric_gate_payload(gate)
        gate_payload["actual"] = numeric_value
        gate_payload["passed"] = numeric_value is not None and numeric_value >= gate.minimum
        results.append(gate_payload)
    return results


def metric_gate_payload(gate: MetricGate) -> dict[str, Any]:
    payload: dict[str, Any] = {"name": gate.name, "minimum": gate.minimum}
    if gate.target is not None:
        payload["target"] = gate.target
    return payload


if __name__ == "__main__":
    sys.exit(main())
