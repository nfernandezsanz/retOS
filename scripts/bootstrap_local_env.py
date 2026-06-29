#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def bootstrap_env(root: Path = ROOT) -> str:
    source = root / ".env.example"
    target = root / ".env"
    if not source.is_file():
        raise SystemExit(f"Missing {source}")
    if target.exists():
        return f"Local environment already exists: {target}"
    shutil.copy2(source, target)
    return f"Created local environment: {target}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a local .env from .env.example without overwriting secrets."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="Repository root. Defaults to the current RetOS checkout.",
    )
    args = parser.parse_args()
    print(bootstrap_env(args.root.resolve()))


if __name__ == "__main__":
    main()
