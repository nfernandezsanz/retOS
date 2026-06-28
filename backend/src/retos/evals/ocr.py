from __future__ import annotations

import json
import textwrap
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from retos.ingestion.scan import ocr_pdf_text


class OCRBenchmarkAdapterError(ValueError):
    pass


@dataclass(frozen=True)
class OCRCaseResult:
    case_id: str
    expected_text: str
    actual_text: str
    character_error_rate: float
    word_error_rate: float
    key_value_recall: float | None
    passed: bool
    failures: tuple[str, ...]


@dataclass(frozen=True)
class OCRQualityReport:
    suite_name: str
    passed: bool
    case_count: int
    character_error_rate: float
    word_error_rate: float
    key_value_recall: float | None
    cases: tuple[OCRCaseResult, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "suite_name": self.suite_name,
            "passed": self.passed,
            "case_count": self.case_count,
            "metrics": {
                "character_error_rate": self.character_error_rate,
                "word_error_rate": self.word_error_rate,
                **(
                    {"key_value_recall": self.key_value_recall}
                    if self.key_value_recall is not None
                    else {}
                ),
            },
            "cases": [
                {
                    "case_id": case.case_id,
                    "expected_text": case.expected_text,
                    "actual_text": case.actual_text,
                    "character_error_rate": case.character_error_rate,
                    "word_error_rate": case.word_error_rate,
                    "key_value_recall": case.key_value_recall,
                    "passed": case.passed,
                    "failures": list(case.failures),
                }
                for case in self.cases
            ],
        }

    def to_markdown(self) -> str:
        rows = [
            f"# OCR Quality Report: {self.suite_name}",
            "",
            f"Status: {'PASS' if self.passed else 'FAIL'}",
            "",
            "| Metric | Score |",
            "| --- | ---: |",
            f"| Character error rate | {self.character_error_rate:.4f} |",
            f"| Word error rate | {self.word_error_rate:.4f} |",
        ]
        if self.key_value_recall is not None:
            rows.append(f"| Key-value recall | {self.key_value_recall:.4f} |")
        rows.extend(
            [
                "",
                "| Case | Status | CER | WER | KV recall | Failures |",
                "| --- | --- | ---: | ---: | ---: | --- |",
            ]
        )
        rows.extend(
            (
                f"| {case.case_id} | {'PASS' if case.passed else 'FAIL'} | "
                f"{case.character_error_rate:.4f} | {case.word_error_rate:.4f} | "
                f"{format_optional_metric(case.key_value_recall)} | "
                f"{', '.join(case.failures) if case.failures else '-'} |"
            )
            for case in self.cases
        )
        return "\n".join(rows) + "\n"


@dataclass(frozen=True)
class OCRQualityCase:
    case_id: str
    expected_text: str
    input_path: Path | None = None
    expected_key_values: dict[str, str] | None = None


@dataclass(frozen=True)
class OCRBenchmarkOptions:
    max_cases: int | None = None
    dataset_format: str = "manifest"


def normalize_ocr_text(value: str) -> str:
    return " ".join(value.casefold().split())


def normalize_ocr_tokens(value: str) -> tuple[str, ...]:
    tokens: list[str] = []
    for token in normalize_ocr_text(value).split():
        normalized = "".join(character for character in token if character.isalnum())
        if normalized:
            tokens.append(normalized)
    return tuple(tokens)


def edit_distance(left: Sequence[str], right: Sequence[str]) -> int:
    if not left:
        return len(right)
    if not right:
        return len(left)

    previous = list(range(len(right) + 1))
    for left_index, left_value in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_value in enumerate(right, start=1):
            substitution_cost = 0 if left_value == right_value else 1
            current.append(
                min(
                    previous[right_index] + 1,
                    current[right_index - 1] + 1,
                    previous[right_index - 1] + substitution_cost,
                )
            )
        previous = current
    return previous[-1]


def error_rate(expected: Sequence[str], actual: Sequence[str]) -> float:
    if not expected:
        return 0.0 if not actual else 1.0
    return edit_distance(expected, actual) / len(expected)


def format_optional_metric(value: float | None) -> str:
    return "-" if value is None else f"{value:.4f}"


def normalize_key_value_map(values: dict[str, str] | None) -> dict[str, str]:
    if values is None:
        return {}
    normalized: dict[str, str] = {}
    for key, value in values.items():
        normalized_key = normalize_ocr_text(str(key))
        normalized_value = normalize_ocr_text(str(value))
        if normalized_key and normalized_value:
            normalized[normalized_key] = normalized_value
    return normalized


def key_value_recall(expected_key_values: dict[str, str] | None, actual_text: str) -> float | None:
    expected = normalize_key_value_map(expected_key_values)
    if not expected:
        return None
    actual = normalize_ocr_text(actual_text)
    matched = sum(
        1
        for key, value in expected.items()
        if key in actual and value in actual and actual.find(key) <= actual.find(value)
    )
    return matched / len(expected)


def score_ocr_text(
    *,
    case_id: str,
    expected_text: str,
    actual_text: str,
    max_character_error_rate: float,
    max_word_error_rate: float,
    expected_key_values: dict[str, str] | None = None,
) -> OCRCaseResult:
    normalized_expected = normalize_ocr_text(expected_text)
    normalized_actual = normalize_ocr_text(actual_text)
    character_error_rate = error_rate(tuple(normalized_expected), tuple(normalized_actual))
    word_error_rate = error_rate(
        normalize_ocr_tokens(expected_text),
        normalize_ocr_tokens(actual_text),
    )
    key_values_recall = key_value_recall(expected_key_values, actual_text)
    failures: list[str] = []
    if character_error_rate > max_character_error_rate:
        failures.append("character_error_rate")
    if word_error_rate > max_word_error_rate:
        failures.append("word_error_rate")
    if key_values_recall is not None and key_values_recall < 1.0:
        failures.append("key_value_recall")
    return OCRCaseResult(
        case_id=case_id,
        expected_text=expected_text,
        actual_text=actual_text,
        character_error_rate=character_error_rate,
        word_error_rate=word_error_rate,
        key_value_recall=key_values_recall,
        passed=not failures,
        failures=tuple(failures),
    )


def synthetic_ocr_cases() -> tuple[OCRQualityCase, ...]:
    return (
        OCRQualityCase(
            case_id="typed-mission-brief",
            expected_text="Mars rover sample caching mission brief.",
        ),
        OCRQualityCase(
            case_id="typed-safety-note",
            expected_text="Local OCR keeps scanned evidence searchable.",
        ),
    )


def load_ocr_benchmark_cases(
    dataset_path: Path,
    options: OCRBenchmarkOptions | None = None,
) -> tuple[OCRQualityCase, ...]:
    adapter_options = options or OCRBenchmarkOptions()
    if adapter_options.max_cases is not None and adapter_options.max_cases < 1:
        raise OCRBenchmarkAdapterError("max_cases must be greater than zero")
    dataset_format = adapter_options.dataset_format.strip().lower()
    if dataset_format == "manifest":
        cases = load_manifest_cases(dataset_path)
    elif dataset_format == "funsd":
        cases = load_funsd_cases(dataset_path)
    elif dataset_format == "sroie":
        cases = load_sroie_cases(dataset_path)
    else:
        raise OCRBenchmarkAdapterError(f"Unsupported OCR benchmark format: {dataset_format}")
    if adapter_options.max_cases is not None:
        return tuple(cases[: adapter_options.max_cases])
    return tuple(cases)


def load_manifest_cases(dataset_path: Path) -> tuple[OCRQualityCase, ...]:
    root = dataset_path.parent
    payload = read_json(dataset_path)
    raw_cases = payload.get("cases") if isinstance(payload, dict) else payload
    if not isinstance(raw_cases, list):
        raise OCRBenchmarkAdapterError("OCR benchmark manifest must contain a cases list")
    cases: list[OCRQualityCase] = []
    for index, item in enumerate(raw_cases):
        if not isinstance(item, dict):
            raise OCRBenchmarkAdapterError(f"Expected OCR manifest cases[{index}] to be an object")
        case_id = require_string(item, "case_id")
        expected_text = require_string(item, "expected_text")
        input_path = resolve_case_path(root, require_string(item, "input_path"))
        expected_key_values = optional_string_map(item, "expected_key_values")
        cases.append(
            OCRQualityCase(
                case_id=case_id,
                expected_text=expected_text,
                input_path=input_path,
                expected_key_values=expected_key_values,
            )
        )
    return tuple(cases)


def load_funsd_cases(dataset_path: Path) -> tuple[OCRQualityCase, ...]:
    root = dataset_path if dataset_path.is_dir() else dataset_path.parent
    annotations_root = root / "annotations"
    images_root = root / "images"
    if not annotations_root.exists() or not annotations_root.is_dir():
        raise OCRBenchmarkAdapterError("FUNSD dataset must contain an annotations directory")
    cases: list[OCRQualityCase] = []
    for annotation_path in sorted(annotations_root.glob("*.json")):
        payload = read_json(annotation_path)
        form = payload.get("form")
        if not isinstance(form, list):
            raise OCRBenchmarkAdapterError(
                f"FUNSD annotation {annotation_path.name} missing form list"
            )
        expected_text = " ".join(
            str(item.get("text", "")).strip()
            for item in form
            if isinstance(item, dict) and str(item.get("text", "")).strip()
        )
        if not expected_text:
            raise OCRBenchmarkAdapterError(f"FUNSD annotation {annotation_path.name} has no text")
        image_path = matching_image_path(images_root, annotation_path.stem)
        cases.append(
            OCRQualityCase(
                case_id=f"funsd-{annotation_path.stem}",
                expected_text=expected_text,
                input_path=image_path,
                expected_key_values=key_values_from_funsd_form(form),
            )
        )
    return tuple(cases)


def load_sroie_cases(dataset_path: Path) -> tuple[OCRQualityCase, ...]:
    root = dataset_path if dataset_path.is_dir() else dataset_path.parent
    box_root = first_existing_directory(root, ("box", "boxes", "ocr", "text"))
    image_root = first_existing_directory(root, ("img", "images"))
    cases: list[OCRQualityCase] = []
    for text_path in sorted(box_root.glob("*.txt")):
        expected_text = text_from_sroie_boxes(text_path)
        if not expected_text:
            raise OCRBenchmarkAdapterError(f"SROIE text file {text_path.name} has no text")
        image_path = matching_image_path(image_root, text_path.stem)
        cases.append(
            OCRQualityCase(
                case_id=f"sroie-{text_path.stem}",
                expected_text=expected_text,
                input_path=image_path,
                expected_key_values=key_values_from_sroie_entities(root, text_path.stem),
            )
        )
    return tuple(cases)


def write_image_only_pdf(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1600, 900), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=48)
    wrapped = "\n".join(textwrap.wrap(text, width=36))
    draw.multiline_text((96, 96), wrapped, fill="black", font=font, spacing=18)
    image.save(path, "PDF", resolution=200.0)


def run_ocr_quality_suite(
    *,
    work_dir: Path,
    suite_name: str = "ocr-smoke",
    cases: tuple[OCRQualityCase, ...] | None = None,
    max_character_error_rate: float = 0.20,
    max_word_error_rate: float = 0.35,
    max_pages: int = 1,
) -> OCRQualityReport:
    work_dir.mkdir(parents=True, exist_ok=True)
    results: list[OCRCaseResult] = []
    for case in cases or synthetic_ocr_cases():
        input_path = case.input_path
        if input_path is None:
            input_path = work_dir / f"{case.case_id}.pdf"
            write_image_only_pdf(input_path, case.expected_text)
        actual_text = ocr_pdf_text(
            ocr_input_pdf_bytes(input_path, work_dir=work_dir),
            max_pages=max_pages,
        )
        results.append(
            score_ocr_text(
                case_id=case.case_id,
                expected_text=case.expected_text,
                actual_text=actual_text,
                max_character_error_rate=max_character_error_rate,
                max_word_error_rate=max_word_error_rate,
                expected_key_values=case.expected_key_values,
            )
        )

    case_count = len(results)
    character_error_rate = (
        sum(case.character_error_rate for case in results) / case_count if case_count else 0.0
    )
    word_error_rate = (
        sum(case.word_error_rate for case in results) / case_count if case_count else 0.0
    )
    key_value_results = [
        case.key_value_recall for case in results if case.key_value_recall is not None
    ]
    average_key_value_recall = (
        sum(key_value_results) / len(key_value_results) if key_value_results else None
    )
    return OCRQualityReport(
        suite_name=suite_name,
        passed=all(case.passed for case in results),
        case_count=case_count,
        character_error_rate=character_error_rate,
        word_error_rate=word_error_rate,
        key_value_recall=average_key_value_recall,
        cases=tuple(results),
    )


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise OCRBenchmarkAdapterError(f"Could not read OCR benchmark file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise OCRBenchmarkAdapterError(f"OCR benchmark file is not valid JSON: {path}") from exc


def require_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise OCRBenchmarkAdapterError(f"Expected {key!r} to be a non-empty string")
    return value.strip()


def optional_string_map(payload: dict[str, Any], key: str) -> dict[str, str] | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise OCRBenchmarkAdapterError(f"Expected {key!r} to be an object")
    result: dict[str, str] = {}
    for raw_key, raw_value in value.items():
        if not isinstance(raw_key, str) or not isinstance(raw_value, str):
            raise OCRBenchmarkAdapterError(f"Expected {key!r} keys and values to be strings")
        if raw_key.strip() and raw_value.strip():
            result[raw_key.strip()] = raw_value.strip()
    return result or None


def resolve_case_path(root: Path, value: str) -> Path:
    raw_path = Path(value).expanduser()
    candidate = raw_path if raw_path.is_absolute() else root / raw_path
    resolved = candidate.resolve(strict=False)
    root_resolved = root.resolve(strict=False)
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise OCRBenchmarkAdapterError("OCR benchmark input_path must stay inside dataset root")
    if not resolved.exists() or not resolved.is_file():
        raise OCRBenchmarkAdapterError(f"OCR benchmark input file not found: {resolved}")
    return resolved


def matching_image_path(root: Path, stem: str) -> Path:
    for extension in (".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"):
        candidate = root / f"{stem}{extension}"
        if candidate.exists() and candidate.is_file():
            return candidate
    raise OCRBenchmarkAdapterError(f"Could not find benchmark image for {stem!r}")


def first_existing_directory(root: Path, names: tuple[str, ...]) -> Path:
    for name in names:
        candidate = root / name
        if candidate.exists() and candidate.is_dir():
            return candidate
    raise OCRBenchmarkAdapterError(
        f"OCR benchmark dataset missing one of these directories: {', '.join(names)}"
    )


def text_from_sroie_boxes(path: Path) -> str:
    lines: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split(",", 8)
        text = parts[-1].strip() if parts else ""
        if text:
            lines.append(text)
    return " ".join(lines)


def key_values_from_funsd_form(form: list[Any]) -> dict[str, str] | None:
    by_id = {
        item["id"]: item
        for item in form
        if isinstance(item, dict) and isinstance(item.get("id"), int)
    }
    key_values: dict[str, str] = {}
    for item in by_id.values():
        if item.get("label") != "question":
            continue
        key = str(item.get("text", "")).strip()
        if not key:
            continue
        linked_values = []
        for link in item.get("linking", []):
            if not isinstance(link, list) or len(link) != 2:
                continue
            target = by_id.get(link[1])
            if target is None or target.get("label") != "answer":
                continue
            value = str(target.get("text", "")).strip()
            if value:
                linked_values.append(value)
        if linked_values:
            key_values[key] = " ".join(linked_values)
    return key_values or None


def key_values_from_sroie_entities(root: Path, stem: str) -> dict[str, str] | None:
    entities_root = first_existing_directory_or_none(
        root,
        ("entities", "entity", "key", "keys"),
    )
    if entities_root is None:
        return None
    for extension in (".json", ".txt"):
        candidate = entities_root / f"{stem}{extension}"
        if candidate.exists() and candidate.is_file():
            if extension == ".json":
                payload = read_json(candidate)
                if not isinstance(payload, dict):
                    raise OCRBenchmarkAdapterError(
                        f"SROIE entity file {candidate.name} must contain an object"
                    )
                return {
                    str(key).strip(): str(value).strip()
                    for key, value in payload.items()
                    if str(key).strip() and str(value).strip()
                } or None
            return key_values_from_sroie_text_entities(candidate)
    return None


def key_values_from_sroie_text_entities(path: Path) -> dict[str, str] | None:
    key_values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
        elif "," in line:
            key, value = line.split(",", 1)
        else:
            continue
        if key.strip() and value.strip():
            key_values[key.strip()] = value.strip()
    return key_values or None


def first_existing_directory_or_none(root: Path, names: tuple[str, ...]) -> Path | None:
    for name in names:
        candidate = root / name
        if candidate.exists() and candidate.is_dir():
            return candidate
    return None


def ocr_input_pdf_bytes(input_path: Path, *, work_dir: Path) -> bytes:
    if input_path.suffix.lower() == ".pdf":
        return input_path.read_bytes()
    converted_path = work_dir / f"{input_path.stem}.benchmark.pdf"
    with Image.open(input_path) as image:
        image.convert("RGB").save(converted_path, "PDF", resolution=200.0)
    return converted_path.read_bytes()
