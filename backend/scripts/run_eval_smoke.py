from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from pytesseract import TesseractNotFoundError

from retos.evals.datasets import (
    DatasetAdapterError,
    HotpotQAAdapterOptions,
    NaturalQuestionsAdapterOptions,
    SquadAdapterOptions,
    load_hotpotqa_cases,
    load_natural_questions_cases,
    load_squad_v2_cases,
)
from retos.evals.ocr import (
    OCRBenchmarkAdapterError,
    OCRBenchmarkOptions,
    OCRQualityReport,
    load_ocr_benchmark_cases,
    run_ocr_quality_suite,
)
from retos.evals.reports import write_report_files
from retos.evals.smoke import EvalSuiteReport, run_smoke_eval_suite


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run RetOS local smoke evals.")
    parser.add_argument(
        "--suite",
        choices=(
            "smoke",
            "squad",
            "hotpotqa",
            "natural-questions",
            "ocr-smoke",
            "ocr-benchmark",
        ),
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
        "--dataset-format",
        choices=("manifest", "funsd", "sroie"),
        default="manifest",
        help="Dataset adapter for --suite ocr-benchmark.",
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
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=None,
        help="Optional directory where JSON and Markdown reports should be written.",
    )
    parser.add_argument(
        "--report-stem",
        default=None,
        help="Optional report filename stem. Defaults to the suite name.",
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
                dataset_format=args.dataset_format,
                report_dir=args.report_dir,
                report_stem=args.report_stem,
            )
    return run(
        index_root=args.index_root,
        output_format=args.format,
        suite=args.suite,
        dataset_path=args.dataset_path,
        max_cases=args.max_cases,
        dataset_format=args.dataset_format,
        report_dir=args.report_dir,
        report_stem=args.report_stem,
    )


def run(
    *,
    index_root: Path,
    output_format: str,
    suite: str,
    dataset_path: Path | None,
    max_cases: int | None,
    dataset_format: str = "manifest",
    report_dir: Path | None = None,
    report_stem: str | None = None,
) -> int:
    try:
        report = build_report(
            index_root=index_root,
            suite=suite,
            dataset_path=dataset_path,
            max_cases=max_cases,
            dataset_format=dataset_format,
        )
    except DatasetAdapterError as exc:
        print(f"Eval dataset error: {exc}", file=sys.stderr)
        return 2
    except OCRBenchmarkAdapterError as exc:
        print(f"OCR benchmark dataset error: {exc}", file=sys.stderr)
        return 2
    except TesseractNotFoundError:
        print(
            "OCR eval error: tesseract is required for --suite ocr-smoke. "
            "Install tesseract locally or run the suite inside the RetOS backend image.",
            file=sys.stderr,
        )
        return 2
    if output_format == "markdown":
        print(report.to_markdown())
    else:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    if report_dir is not None:
        json_path, markdown_path = write_report_files(
            report=report,
            report_dir=report_dir,
            report_stem=report_stem,
        )
        print(f"Wrote eval reports: {json_path} {markdown_path}", file=sys.stderr)
    return 0 if report.passed else 1


def build_report(
    *,
    index_root: Path,
    suite: str,
    dataset_path: Path | None,
    max_cases: int | None,
    dataset_format: str,
) -> EvalSuiteReport | OCRQualityReport:
    if suite == "smoke":
        return run_smoke_eval_suite(index_root=index_root)
    if suite == "ocr-smoke":
        return run_ocr_quality_suite(work_dir=index_root / "ocr")
    if suite == "ocr-benchmark":
        if dataset_path is None:
            raise OCRBenchmarkAdapterError("--dataset-path is required for OCR benchmark suites")
        cases = load_ocr_benchmark_cases(
            dataset_path,
            OCRBenchmarkOptions(max_cases=max_cases, dataset_format=dataset_format),
        )
        if not cases:
            raise OCRBenchmarkAdapterError("OCR benchmark dataset produced no eval cases")
        return run_ocr_quality_suite(
            work_dir=index_root / "ocr-benchmark",
            suite_name=f"ocr-{dataset_format}",
            cases=cases,
        )
    if max_cases is not None and max_cases < 1:
        raise DatasetAdapterError("--max-cases must be greater than zero")
    if dataset_path is None:
        raise DatasetAdapterError("--dataset-path is required for dataset-backed suites")
    if suite == "squad":
        cases = load_squad_v2_cases(
            dataset_path,
            SquadAdapterOptions(max_cases=max_cases),
        )
        suite_name = "squad-v2"
    elif suite == "hotpotqa":
        cases = load_hotpotqa_cases(
            dataset_path,
            HotpotQAAdapterOptions(max_cases=max_cases),
        )
        suite_name = "hotpotqa"
    else:
        cases = load_natural_questions_cases(
            dataset_path,
            NaturalQuestionsAdapterOptions(max_cases=max_cases),
        )
        suite_name = "natural-questions"
    if not cases:
        raise DatasetAdapterError(f"{suite_name} dataset produced no eval cases")
    return run_smoke_eval_suite(
        index_root=index_root,
        suite_name=suite_name,
        cases=cases,
    )


if __name__ == "__main__":
    sys.exit(main())
