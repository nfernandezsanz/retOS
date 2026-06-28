from __future__ import annotations

import textwrap
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from retos.ingestion.scan import ocr_pdf_text


@dataclass(frozen=True)
class OCRCaseResult:
    case_id: str
    expected_text: str
    actual_text: str
    character_error_rate: float
    word_error_rate: float
    passed: bool
    failures: tuple[str, ...]


@dataclass(frozen=True)
class OCRQualityReport:
    suite_name: str
    passed: bool
    case_count: int
    character_error_rate: float
    word_error_rate: float
    cases: tuple[OCRCaseResult, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "suite_name": self.suite_name,
            "passed": self.passed,
            "case_count": self.case_count,
            "metrics": {
                "character_error_rate": self.character_error_rate,
                "word_error_rate": self.word_error_rate,
            },
            "cases": [
                {
                    "case_id": case.case_id,
                    "expected_text": case.expected_text,
                    "actual_text": case.actual_text,
                    "character_error_rate": case.character_error_rate,
                    "word_error_rate": case.word_error_rate,
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
            "",
            "| Case | Status | CER | WER | Failures |",
            "| --- | --- | ---: | ---: | --- |",
        ]
        rows.extend(
            (
                f"| {case.case_id} | {'PASS' if case.passed else 'FAIL'} | "
                f"{case.character_error_rate:.4f} | {case.word_error_rate:.4f} | "
                f"{', '.join(case.failures) if case.failures else '-'} |"
            )
            for case in self.cases
        )
        return "\n".join(rows) + "\n"


@dataclass(frozen=True)
class OCRQualityCase:
    case_id: str
    expected_text: str


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


def score_ocr_text(
    *,
    case_id: str,
    expected_text: str,
    actual_text: str,
    max_character_error_rate: float,
    max_word_error_rate: float,
) -> OCRCaseResult:
    normalized_expected = normalize_ocr_text(expected_text)
    normalized_actual = normalize_ocr_text(actual_text)
    character_error_rate = error_rate(tuple(normalized_expected), tuple(normalized_actual))
    word_error_rate = error_rate(
        normalize_ocr_tokens(expected_text),
        normalize_ocr_tokens(actual_text),
    )
    failures: list[str] = []
    if character_error_rate > max_character_error_rate:
        failures.append("character_error_rate")
    if word_error_rate > max_word_error_rate:
        failures.append("word_error_rate")
    return OCRCaseResult(
        case_id=case_id,
        expected_text=expected_text,
        actual_text=actual_text,
        character_error_rate=character_error_rate,
        word_error_rate=word_error_rate,
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
        pdf_path = work_dir / f"{case.case_id}.pdf"
        write_image_only_pdf(pdf_path, case.expected_text)
        actual_text = ocr_pdf_text(pdf_path.read_bytes(), max_pages=max_pages)
        results.append(
            score_ocr_text(
                case_id=case.case_id,
                expected_text=case.expected_text,
                actual_text=actual_text,
                max_character_error_rate=max_character_error_rate,
                max_word_error_rate=max_word_error_rate,
            )
        )

    case_count = len(results)
    character_error_rate = (
        sum(case.character_error_rate for case in results) / case_count if case_count else 0.0
    )
    word_error_rate = (
        sum(case.word_error_rate for case in results) / case_count if case_count else 0.0
    )
    return OCRQualityReport(
        suite_name=suite_name,
        passed=all(case.passed for case in results),
        case_count=case_count,
        character_error_rate=character_error_rate,
        word_error_rate=word_error_rate,
        cases=tuple(results),
    )
