from pathlib import Path

from retos.evals.ocr import (
    OCRQualityCase,
    edit_distance,
    error_rate,
    normalize_ocr_text,
    normalize_ocr_tokens,
    run_ocr_quality_suite,
    score_ocr_text,
)


def test_ocr_text_normalization_and_edit_distance() -> None:
    assert normalize_ocr_text(" Mars\nROVER   ") == "mars rover"
    assert normalize_ocr_tokens("Searchable, audited evidence.") == (
        "searchable",
        "audited",
        "evidence",
    )
    assert edit_distance(tuple("kitten"), tuple("sitting")) == 3
    assert error_rate(tuple("abcd"), tuple("abxd")) == 0.25


def test_ocr_score_reports_character_and_word_error_rates() -> None:
    result = score_ocr_text(
        case_id="fixture",
        expected_text="Local OCR keeps scanned evidence searchable.",
        actual_text="Local OCR keeps scanned evidence searchable",
        max_character_error_rate=0.01,
        max_word_error_rate=0.10,
    )

    assert result.passed is False
    assert result.character_error_rate > 0
    assert result.word_error_rate == 0
    assert result.failures == ("character_error_rate",)


def test_ocr_quality_suite_uses_pipeline_ocr_and_reports_metrics(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    def fake_ocr(raw: bytes, *, max_pages: int) -> str:
        assert raw.startswith(b"%PDF")
        assert max_pages == 1
        return "Local OCR keeps scanned evidence searchable."

    monkeypatch.setattr("retos.evals.ocr.ocr_pdf_text", fake_ocr)

    report = run_ocr_quality_suite(
        work_dir=tmp_path,
        cases=(
            OCRQualityCase(
                case_id="local-ocr",
                expected_text="Local OCR keeps scanned evidence searchable.",
            ),
        ),
    )

    assert report.suite_name == "ocr-smoke"
    assert report.passed is True
    assert report.case_count == 1
    assert report.character_error_rate == 0
    assert report.word_error_rate == 0
    assert report.to_dict()["metrics"] == {
        "character_error_rate": 0.0,
        "word_error_rate": 0.0,
    }
    assert "OCR Quality Report: ocr-smoke" in report.to_markdown()
    assert (tmp_path / "local-ocr.pdf").exists()


def test_ocr_quality_suite_fails_when_thresholds_are_exceeded(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("retos.evals.ocr.ocr_pdf_text", lambda raw, max_pages: "wrong")

    report = run_ocr_quality_suite(
        work_dir=tmp_path,
        cases=(
            OCRQualityCase(
                case_id="bad-ocr",
                expected_text="Expected scanned evidence.",
            ),
        ),
    )

    assert report.passed is False
    assert report.cases[0].failures == ("character_error_rate", "word_error_rate")
