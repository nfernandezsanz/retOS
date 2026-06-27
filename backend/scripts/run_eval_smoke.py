from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from retos.evals.datasets import DatasetAdapterError, SquadAdapterOptions, load_squad_v2_cases
from retos.evals.smoke import EvalSuiteReport, run_smoke_eval_suite


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run RetOS local smoke evals.")
    parser.add_argument(
        "--suite",
        choices=("smoke", "squad"),
        default="smoke",
        help="Eval suite to run.",
    )
    parser.add_argument(
        "--dataset-path",
        type=Path,
        default=None,
        help="Path to an opt-in dataset file for dataset-backed suites.",
    )
    parser.add_argument(
        "--max-cases",
        type=int,
        default=None,
        help="Maximum dataset cases to load for dataset-backed suites.",
    )
    parser.add_argument(
        "--index-root",
        type=Path,
        default=None,
        help="Directory for temporary Tantivy eval indexes.",
    )
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="Report output format.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.index_root is None:
        with tempfile.TemporaryDirectory(prefix="retos-eval-index-") as temp_dir:
            return run(
                index_root=Path(temp_dir),
                output_format=args.format,
                suite=args.suite,
                dataset_path=args.dataset_path,
                max_cases=args.max_cases,
            )
    return run(
        index_root=args.index_root,
        output_format=args.format,
        suite=args.suite,
        dataset_path=args.dataset_path,
        max_cases=args.max_cases,
    )


def run(
    *,
    index_root: Path,
    output_format: str,
    suite: str,
    dataset_path: Path | None,
    max_cases: int | None,
) -> int:
    try:
        report = build_report(
            index_root=index_root,
            suite=suite,
            dataset_path=dataset_path,
            max_cases=max_cases,
        )
    except DatasetAdapterError as exc:
        print(f"Eval dataset error: {exc}", file=sys.stderr)
        return 2
    if output_format == "markdown":
        print(report.to_markdown())
    else:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 0 if report.passed else 1


def build_report(
    *,
    index_root: Path,
    suite: str,
    dataset_path: Path | None,
    max_cases: int | None,
) -> EvalSuiteReport:
    if suite == "smoke":
        return run_smoke_eval_suite(index_root=index_root)
    if max_cases is not None and max_cases < 1:
        raise DatasetAdapterError("--max-cases must be greater than zero")
    if dataset_path is None:
        raise DatasetAdapterError("--dataset-path is required for the SQuAD suite")
    cases = load_squad_v2_cases(
        dataset_path,
        SquadAdapterOptions(max_cases=max_cases),
    )
    if not cases:
        raise DatasetAdapterError("SQuAD dataset produced no eval cases")
    return run_smoke_eval_suite(
        index_root=index_root,
        suite_name="squad-v2",
        cases=cases,
    )


if __name__ == "__main__":
    sys.exit(main())
