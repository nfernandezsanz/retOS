from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


class DatasetFetchError(RuntimeError):
    pass


@dataclass(frozen=True)
class DatasetProfile:
    name: str
    suite: str
    url: str | None
    output_name: str
    description: str
    license_note: str
    source_homepage: str
    sampler: Callable[[Path, Path, int], int] | None


DATASET_PROFILES: dict[str, DatasetProfile] = {
    "squad-dev-v2": DatasetProfile(
        name="squad-dev-v2",
        suite="squad",
        url="https://rajpurkar.github.io/SQuAD-explorer/dataset/dev-v2.0.json",
        output_name="squad-dev-v2-sample.json",
        description="SQuAD 2.0 development set with answerable and unanswerable QA cases.",
        license_note="SQuAD data is distributed by the Stanford SQuAD project.",
        source_homepage="https://rajpurkar.github.io/SQuAD-explorer/",
        sampler=lambda src, dest, limit: write_squad_sample(src, dest, limit),
    ),
    "hotpotqa-dev-distractor": DatasetProfile(
        name="hotpotqa-dev-distractor",
        suite="hotpotqa",
        url="http://curtis.ml.cmu.edu/datasets/hotpot/hotpot_dev_distractor_v1.json",
        output_name="hotpotqa-dev-distractor-sample.json",
        description="HotpotQA distractor development set for multi-hop retrieval evaluation.",
        license_note="HotpotQA is distributed under CC BY-SA 4.0.",
        source_homepage="https://hotpotqa.github.io/",
        sampler=lambda src, dest, limit: write_json_list_sample(src, dest, limit),
    ),
    "nq-open-train": DatasetProfile(
        name="nq-open-train",
        suite="natural-questions-open",
        url=(
            "https://raw.githubusercontent.com/google-research-datasets/"
            "natural-questions/master/nq_open/NQ-open.train.jsonl"
        ),
        output_name="nq-open-train-sample.jsonl",
        description=(
            "Natural Questions Open training JSONL. This profile is fetched for "
            "research inspection; RetOS full Natural Questions evals still expect "
            "the annotated document-shape adapter input."
        ),
        license_note="Natural Questions tooling is published by Google under Apache-2.0.",
        source_homepage="https://github.com/google-research-datasets/natural-questions",
        sampler=lambda src, dest, limit: write_jsonl_sample(src, dest, limit),
    ),
    "funsd": DatasetProfile(
        name="funsd",
        suite="ocr-benchmark",
        url=None,
        output_name="funsd",
        description=(
            "FUNSD forms dataset for OCR, layout, and form understanding. Download "
            "manually after reviewing the dataset license."
        ),
        license_note=(
            "FUNSD is provided for non-commercial research and educational use; "
            "review the official license before downloading."
        ),
        source_homepage="https://guillaumejaume.github.io/FUNSD/download/",
        sampler=None,
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch opt-in public eval dataset samples for RetOS."
    )
    parser.add_argument(
        "profile",
        nargs="?",
        choices=tuple(DATASET_PROFILES),
        help="Dataset profile to fetch. Omit with --list to inspect available profiles.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("evals/datasets"),
        help="Directory where the sampled dataset should be written.",
    )
    parser.add_argument(
        "--max-records",
        type=int,
        default=100,
        help="Maximum top-level records or QA cases to keep in the sample.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List dataset profiles without downloading anything.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing sampled dataset file.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.list:
        print(profile_table())
        return 0
    if args.profile is None:
        print("Choose a dataset profile or pass --list.", file=sys.stderr)
        return 2
    try:
        result = fetch_profile(
            profile=DATASET_PROFILES[args.profile],
            output_dir=args.output_dir,
            max_records=args.max_records,
            force=args.force,
        )
    except DatasetFetchError as exc:
        print(f"Dataset fetch error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def profile_table() -> str:
    rows = [
        "Available eval dataset profiles:",
        "",
        "| Profile | Suite | Source |",
        "| --- | --- | --- |",
    ]
    for profile in DATASET_PROFILES.values():
        rows.append(f"| {profile.name} | {profile.suite} | {profile.source_homepage} |")
    return "\n".join(rows)


def fetch_profile(
    *,
    profile: DatasetProfile,
    output_dir: Path,
    max_records: int,
    force: bool = False,
) -> dict[str, object]:
    if max_records < 1:
        raise DatasetFetchError("--max-records must be greater than zero")
    if profile.url is None or profile.sampler is None:
        raise DatasetFetchError(
            f"{profile.name} requires manual download from {profile.source_homepage}"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / profile.output_name
    if output_path.exists() and not force:
        raise DatasetFetchError(f"Refusing to overwrite existing dataset: {output_path}")

    with tempfile.TemporaryDirectory(prefix="retos-eval-dataset-") as temp_dir:
        downloaded_path = Path(temp_dir) / profile.output_name
        download_file(profile.url, downloaded_path)
        record_count = profile.sampler(downloaded_path, output_path, max_records)

    return {
        "profile": profile.name,
        "suite": profile.suite,
        "path": str(output_path),
        "records": record_count,
        "source": profile.source_homepage,
        "license_note": profile.license_note,
    }


def download_file(url: str, output_path: Path) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise DatasetFetchError(f"Unsupported dataset URL scheme: {parsed.scheme}")
    try:
        with (
            urllib.request.urlopen(url, timeout=60) as response,  # noqa: S310
            output_path.open("wb") as destination,
        ):
            shutil.copyfileobj(response, destination)
    except (urllib.error.URLError, OSError) as exc:
        raise DatasetFetchError(f"Could not download {url}") from exc


def write_squad_sample(source_path: Path, output_path: Path, max_cases: int) -> int:
    payload = read_json_object(source_path)
    data = payload.get("data")
    if not isinstance(data, list):
        raise DatasetFetchError("SQuAD payload missing data list")

    sampled_data: list[dict[str, Any]] = []
    remaining = max_cases
    for article in data:
        if remaining <= 0:
            break
        if not isinstance(article, dict):
            continue
        sampled_article = dict(article)
        sampled_paragraphs: list[dict[str, Any]] = []
        paragraphs = article.get("paragraphs")
        if not isinstance(paragraphs, list):
            continue
        for paragraph in paragraphs:
            if remaining <= 0:
                break
            if not isinstance(paragraph, dict):
                continue
            qas = paragraph.get("qas")
            if not isinstance(qas, list):
                continue
            sampled_qas = qas[:remaining]
            if sampled_qas:
                sampled_paragraph = dict(paragraph)
                sampled_paragraph["qas"] = sampled_qas
                sampled_paragraphs.append(sampled_paragraph)
                remaining -= len(sampled_qas)
        if sampled_paragraphs:
            sampled_article["paragraphs"] = sampled_paragraphs
            sampled_data.append(sampled_article)

    record_count = max_cases - remaining
    if record_count == 0:
        raise DatasetFetchError("SQuAD payload produced no QA cases")
    write_json(output_path, {"version": payload.get("version", "v2.0"), "data": sampled_data})
    return record_count


def write_json_list_sample(source_path: Path, output_path: Path, max_records: int) -> int:
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise DatasetFetchError("Expected dataset payload to be a list")
    sampled = payload[:max_records]
    write_json(output_path, sampled)
    return len(sampled)


def write_jsonl_sample(source_path: Path, output_path: Path, max_records: int) -> int:
    count = 0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with (
        source_path.open(encoding="utf-8") as source,
        output_path.open("w", encoding="utf-8") as destination,
    ):
        for line in source:
            if count >= max_records:
                break
            stripped = line.strip()
            if not stripped:
                continue
            json.loads(stripped)
            destination.write(stripped + "\n")
            count += 1
    if count == 0:
        raise DatasetFetchError("JSONL payload produced no records")
    return count


def read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise DatasetFetchError("Expected dataset payload to be an object")
    return payload


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
