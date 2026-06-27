from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from retos.evals.smoke import run_smoke_eval_suite


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run RetOS local smoke evals.")
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
            return run(Path(temp_dir), args.format)
    return run(args.index_root, args.format)


def run(index_root: Path, output_format: str) -> int:
    report = run_smoke_eval_suite(index_root=index_root)
    if output_format == "markdown":
        print(report.to_markdown())
    else:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
