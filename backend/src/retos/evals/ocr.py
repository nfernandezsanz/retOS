from __future__ import annotations

import json
import textwrap
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pymupdf
import pytesseract  # type: ignore[import-untyped]
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
    reading_order_accuracy: float | None = None
    layout_iou: float | None = None


@dataclass(frozen=True)
class OCRQualityReport:
    suite_name: str
    passed: bool
    case_count: int
    character_error_rate: float
    word_error_rate: float
    key_value_recall: float | None
    cases: tuple[OCRCaseResult, ...]
    reading_order_accuracy: float | None = None
    layout_iou: float | None = None

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
                **(
                    {"reading_order_accuracy": self.reading_order_accuracy}
                    if self.reading_order_accuracy is not None
                    else {}
                ),
                **({"layout_iou": self.layout_iou} if self.layout_iou is not None else {}),
            },
            "cases": [
                {
                    "case_id": case.case_id,
                    "expected_text": case.expected_text,
                    "actual_text": case.actual_text,
                    "character_error_rate": case.character_error_rate,
                    "word_error_rate": case.word_error_rate,
                    "key_value_recall": case.key_value_recall,
                    "reading_order_accuracy": case.reading_order_accuracy,
                    "layout_iou": case.layout_iou,
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
        if self.reading_order_accuracy is not None:
            rows.append(f"| Reading order accuracy | {self.reading_order_accuracy:.4f} |")
        if self.layout_iou is not None:
            rows.append(f"| Layout IoU | {self.layout_iou:.4f} |")
        rows.extend(
            [
                "",
                "| Case | Status | CER | WER | KV recall | Order | IoU | Failures |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
            ]
        )
        rows.extend(
            (
                f"| {case.case_id} | {'PASS' if case.passed else 'FAIL'} | "
                f"{case.character_error_rate:.4f} | {case.word_error_rate:.4f} | "
                f"{format_optional_metric(case.key_value_recall)} | "
                f"{format_optional_metric(case.reading_order_accuracy)} | "
                f"{format_optional_metric(case.layout_iou)} | "
                f"{', '.join(case.failures) if case.failures else '-'} |"
            )
            for case in self.cases
        )
        return "\n".join(rows) + "\n"


@dataclass(frozen=True)
class OCRLayoutBox:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    page_number: int = 1


@dataclass(frozen=True)
class OCRQualityCase:
    case_id: str
    expected_text: str
    input_path: Path | None = None
    expected_key_values: dict[str, str] | None = None
    expected_layout: tuple[OCRLayoutBox, ...] = ()


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


def normalize_layout_text(value: str) -> str:
    return " ".join(normalize_ocr_tokens(value))


def box_area(box: OCRLayoutBox) -> float:
    return max(0.0, box.x1 - box.x0) * max(0.0, box.y1 - box.y0)


def box_iou(expected: OCRLayoutBox, actual: OCRLayoutBox) -> float:
    if expected.page_number != actual.page_number:
        return 0.0
    intersection_width = max(0.0, min(expected.x1, actual.x1) - max(expected.x0, actual.x0))
    intersection_height = max(0.0, min(expected.y1, actual.y1) - max(expected.y0, actual.y0))
    intersection = intersection_width * intersection_height
    union = box_area(expected) + box_area(actual) - intersection
    return intersection / union if union else 0.0


def layout_scores(
    expected_layout: tuple[OCRLayoutBox, ...],
    actual_layout: tuple[OCRLayoutBox, ...],
) -> tuple[float, float] | None:
    if not expected_layout:
        return None
    if not actual_layout:
        return 0.0, 0.0

    ordered_actual = tuple(
        sorted(actual_layout, key=lambda box: (box.page_number, box.y0, box.x0, box.y1, box.x1))
    )
    used_actual_indexes: set[int] = set()
    matched_actual_indexes: list[int | None] = []
    iou_scores: list[float] = []
    for expected in expected_layout:
        expected_text = normalize_layout_text(expected.text)
        best_index: int | None = None
        best_iou = 0.0
        for index, actual in enumerate(ordered_actual):
            if index in used_actual_indexes:
                continue
            if normalize_layout_text(actual.text) != expected_text:
                continue
            candidate_iou = box_iou(expected, actual)
            if best_index is None or candidate_iou > best_iou:
                best_index = index
                best_iou = candidate_iou
        if best_index is None:
            matched_actual_indexes.append(None)
            iou_scores.append(0.0)
            continue
        used_actual_indexes.add(best_index)
        matched_actual_indexes.append(best_index)
        iou_scores.append(best_iou)

    if len(expected_layout) == 1:
        reading_order_accuracy = 1.0 if matched_actual_indexes[0] is not None else 0.0
    else:
        correct_pairs = 0
        total_pairs = 0
        for left_index, left_actual_index in enumerate(matched_actual_indexes):
            for right_actual_index in matched_actual_indexes[left_index + 1 :]:
                total_pairs += 1
                if left_actual_index is None or right_actual_index is None:
                    continue
                if left_actual_index < right_actual_index:
                    correct_pairs += 1
        reading_order_accuracy = correct_pairs / total_pairs if total_pairs else 0.0
    return reading_order_accuracy, sum(iou_scores) / len(iou_scores)


def score_ocr_text(
    *,
    case_id: str,
    expected_text: str,
    actual_text: str,
    max_character_error_rate: float,
    max_word_error_rate: float,
    expected_key_values: dict[str, str] | None = None,
    expected_layout: tuple[OCRLayoutBox, ...] = (),
    actual_layout: tuple[OCRLayoutBox, ...] = (),
    min_reading_order_accuracy: float = 1.0,
    min_layout_iou: float = 0.50,
) -> OCRCaseResult:
    normalized_expected = normalize_ocr_text(expected_text)
    normalized_actual = normalize_ocr_text(actual_text)
    character_error_rate = error_rate(tuple(normalized_expected), tuple(normalized_actual))
    word_error_rate = error_rate(
        normalize_ocr_tokens(expected_text),
        normalize_ocr_tokens(actual_text),
    )
    key_values_recall = key_value_recall(expected_key_values, actual_text)
    layout_result = layout_scores(expected_layout, actual_layout)
    reading_order_accuracy = layout_result[0] if layout_result is not None else None
    layout_iou = layout_result[1] if layout_result is not None else None
    failures: list[str] = []
    if character_error_rate > max_character_error_rate:
        failures.append("character_error_rate")
    if word_error_rate > max_word_error_rate:
        failures.append("word_error_rate")
    if key_values_recall is not None and key_values_recall < 1.0:
        failures.append("key_value_recall")
    if reading_order_accuracy is not None and reading_order_accuracy < min_reading_order_accuracy:
        failures.append("reading_order_accuracy")
    if layout_iou is not None and layout_iou < min_layout_iou:
        failures.append("layout_iou")
    return OCRCaseResult(
        case_id=case_id,
        expected_text=expected_text,
        actual_text=actual_text,
        character_error_rate=character_error_rate,
        word_error_rate=word_error_rate,
        key_value_recall=key_values_recall,
        reading_order_accuracy=reading_order_accuracy,
        layout_iou=layout_iou,
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
        expected_layout = optional_layout_boxes(item, "expected_layout")
        cases.append(
            OCRQualityCase(
                case_id=case_id,
                expected_text=expected_text,
                input_path=input_path,
                expected_key_values=expected_key_values,
                expected_layout=expected_layout,
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
                expected_layout=layout_from_funsd_form(form),
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
                expected_layout=layout_from_sroie_boxes(text_path),
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
    min_reading_order_accuracy: float = 1.0,
    min_layout_iou: float = 0.50,
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
        actual_layout = (
            ocr_pdf_layout(input_path, work_dir=work_dir, max_pages=max_pages)
            if case.expected_layout
            else ()
        )
        results.append(
            score_ocr_text(
                case_id=case.case_id,
                expected_text=case.expected_text,
                actual_text=actual_text,
                max_character_error_rate=max_character_error_rate,
                max_word_error_rate=max_word_error_rate,
                expected_key_values=case.expected_key_values,
                expected_layout=case.expected_layout,
                actual_layout=actual_layout,
                min_reading_order_accuracy=min_reading_order_accuracy,
                min_layout_iou=min_layout_iou,
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
    reading_order_results = [
        case.reading_order_accuracy for case in results if case.reading_order_accuracy is not None
    ]
    average_reading_order_accuracy = (
        sum(reading_order_results) / len(reading_order_results) if reading_order_results else None
    )
    layout_iou_results = [case.layout_iou for case in results if case.layout_iou is not None]
    average_layout_iou = (
        sum(layout_iou_results) / len(layout_iou_results) if layout_iou_results else None
    )
    return OCRQualityReport(
        suite_name=suite_name,
        passed=all(case.passed for case in results),
        case_count=case_count,
        character_error_rate=character_error_rate,
        word_error_rate=word_error_rate,
        key_value_recall=average_key_value_recall,
        reading_order_accuracy=average_reading_order_accuracy,
        layout_iou=average_layout_iou,
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


def optional_layout_boxes(payload: dict[str, Any], key: str) -> tuple[OCRLayoutBox, ...]:
    value = payload.get(key)
    if value is None:
        return ()
    if not isinstance(value, list):
        raise OCRBenchmarkAdapterError(f"Expected {key!r} to be a list")
    boxes: list[OCRLayoutBox] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise OCRBenchmarkAdapterError(f"Expected {key}[{index}] to be an object")
        text = require_string(item, "text")
        page_number = optional_positive_int(item, "page_number", default=1)
        boxes.append(
            layout_box_from_bbox(text=text, bbox=item.get("bbox"), page_number=page_number)
        )
    return tuple(boxes)


def optional_positive_int(payload: dict[str, Any], key: str, *, default: int) -> int:
    value = payload.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise OCRBenchmarkAdapterError(f"Expected {key!r} to be a positive integer")
    return value


def layout_box_from_bbox(*, text: str, bbox: object, page_number: int = 1) -> OCRLayoutBox:
    if not isinstance(bbox, list) or len(bbox) != 4:
        raise OCRBenchmarkAdapterError("Expected layout bbox to contain four numbers")
    values: list[float] = []
    for value in bbox:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise OCRBenchmarkAdapterError("Expected layout bbox values to be numbers")
        values.append(float(value))
    x0, y0, x1, y1 = values
    if x1 <= x0 or y1 <= y0:
        raise OCRBenchmarkAdapterError("Expected layout bbox to have positive area")
    return OCRLayoutBox(text=text, x0=x0, y0=y0, x1=x1, y1=y1, page_number=page_number)


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


def layout_from_sroie_boxes(path: Path) -> tuple[OCRLayoutBox, ...]:
    boxes: list[OCRLayoutBox] = []
    for line_index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        parts = line.split(",", 8)
        if len(parts) < 9:
            continue
        text = parts[-1].strip()
        if not text:
            continue
        try:
            coordinates = [float(part) for part in parts[:8]]
        except ValueError as exc:
            raise OCRBenchmarkAdapterError(
                f"SROIE text file {path.name} has invalid coordinates on line {line_index}"
            ) from exc
        x_values = coordinates[0::2]
        y_values = coordinates[1::2]
        boxes.append(
            OCRLayoutBox(
                text=text,
                x0=min(x_values),
                y0=min(y_values),
                x1=max(x_values),
                y1=max(y_values),
            )
        )
    return tuple(boxes)


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


def layout_from_funsd_form(form: list[Any]) -> tuple[OCRLayoutBox, ...]:
    boxes: list[OCRLayoutBox] = []
    for item in form:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "")).strip()
        box = item.get("box")
        if not text or box is None:
            continue
        boxes.append(layout_box_from_bbox(text=text, bbox=box))
    return tuple(boxes)


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


def ocr_pdf_layout(input_path: Path, *, work_dir: Path, max_pages: int) -> tuple[OCRLayoutBox, ...]:
    raw = ocr_input_pdf_bytes(input_path, work_dir=work_dir)
    boxes: list[OCRLayoutBox] = []
    with pymupdf.open(stream=raw, filetype="pdf") as document:  # type: ignore[no-untyped-call]
        for page_index, page in enumerate(document):
            if page_index >= max_pages:
                break
            pixmap = page.get_pixmap(
                matrix=pymupdf.Matrix(2, 2),  # type: ignore[no-untyped-call]
                alpha=False,
            )
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            data = pytesseract.image_to_data(
                image,
                lang="eng",
                output_type=pytesseract.Output.DICT,
            )
            text_values = data.get("text", [])
            left_values = data.get("left", [])
            top_values = data.get("top", [])
            width_values = data.get("width", [])
            height_values = data.get("height", [])
            for index, text in enumerate(text_values):
                normalized_text = str(text).strip()
                if not normalized_text:
                    continue
                x0 = float(left_values[index])
                y0 = float(top_values[index])
                width = float(width_values[index])
                height = float(height_values[index])
                if width <= 0 or height <= 0:
                    continue
                boxes.append(
                    OCRLayoutBox(
                        text=normalized_text,
                        x0=x0,
                        y0=y0,
                        x1=x0 + width,
                        y1=y0 + height,
                        page_number=page_index + 1,
                    )
                )
    return tuple(boxes)
