import json
from pathlib import Path

import pytest

from retos.evals.ocr import (
    OCRBenchmarkAdapterError,
    OCRBenchmarkOptions,
    OCRLayoutBox,
    OCRQualityCase,
    edit_distance,
    error_rate,
    key_value_recall,
    load_ocr_benchmark_cases,
    normalize_ocr_text,
    normalize_ocr_tokens,
    ocr_pdf_layout,
    run_ocr_quality_suite,
    score_ocr_text,
    write_image_only_pdf,
)


def test_ocr_text_normalization_and_edit_distance() -> None:
    assert normalize_ocr_text(" Mars\nROVER   ") == "mars rover"
    assert normalize_ocr_tokens("Searchable, audited evidence.") == (
        "searchable",
        "audited",
        "evidence",
    )
    assert edit_distance(tuple("kitten"), tuple("sitting")) == 3
    assert edit_distance((), tuple("abc")) == 3
    assert edit_distance(tuple("abc"), ()) == 3
    assert error_rate(tuple("abcd"), tuple("abxd")) == 0.25
    assert error_rate((), ()) == 0.0
    assert error_rate((), tuple("x")) == 1.0


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


def test_ocr_score_reports_word_failures() -> None:
    result = score_ocr_text(
        case_id="fixture",
        expected_text="Invoice total approved",
        actual_text="Completely different words",
        max_character_error_rate=2.0,
        max_word_error_rate=0.10,
    )

    assert result.passed is False
    assert result.failures == ("word_error_rate",)


def test_ocr_score_reports_key_value_recall() -> None:
    matched = score_ocr_text(
        case_id="receipt",
        expected_text="Store ACME Total 42",
        actual_text="Store ACME Total 42",
        max_character_error_rate=0.0,
        max_word_error_rate=0.0,
        expected_key_values={"Store": "ACME", "Total": "42"},
    )
    missed = score_ocr_text(
        case_id="receipt",
        expected_text="Store ACME Total 42",
        actual_text="Store ACME Total",
        max_character_error_rate=1.0,
        max_word_error_rate=1.0,
        expected_key_values={"Store": "ACME", "Total": "42"},
    )

    assert key_value_recall({"Store": "ACME"}, "store acme total 42") == 1.0
    assert matched.key_value_recall == 1.0
    assert matched.passed is True
    assert missed.key_value_recall == 0.5
    assert missed.failures == ("key_value_recall",)


def test_ocr_score_reports_layout_metrics() -> None:
    expected_layout = (
        OCRLayoutBox(text="Total", x0=0, y0=0, x1=50, y1=20),
        OCRLayoutBox(text="42", x0=60, y0=0, x1=80, y1=20),
    )
    matched = score_ocr_text(
        case_id="receipt",
        expected_text="Total 42",
        actual_text="Total 42",
        max_character_error_rate=0.0,
        max_word_error_rate=0.0,
        expected_layout=expected_layout,
        actual_layout=(
            OCRLayoutBox(text="Total", x0=0, y0=0, x1=50, y1=20),
            OCRLayoutBox(text="42", x0=60, y0=0, x1=80, y1=20),
        ),
    )
    reversed_order = score_ocr_text(
        case_id="receipt",
        expected_text="Total 42",
        actual_text="Total 42",
        max_character_error_rate=0.0,
        max_word_error_rate=0.0,
        expected_layout=expected_layout,
        actual_layout=(
            OCRLayoutBox(text="42", x0=0, y0=0, x1=20, y1=20),
            OCRLayoutBox(text="Total", x0=60, y0=0, x1=110, y1=20),
        ),
    )

    assert matched.passed is True
    assert matched.reading_order_accuracy == 1.0
    assert matched.layout_iou == 1.0
    assert reversed_order.passed is False
    assert reversed_order.reading_order_accuracy == 0.0
    assert reversed_order.failures == ("reading_order_accuracy", "layout_iou")


def test_ocr_score_reports_missing_layout_failures() -> None:
    result = score_ocr_text(
        case_id="receipt",
        expected_text="Total 42",
        actual_text="Total 42",
        max_character_error_rate=0.0,
        max_word_error_rate=0.0,
        expected_layout=(OCRLayoutBox(text="Total", x0=0, y0=0, x1=50, y1=20),),
        actual_layout=(),
    )

    assert result.reading_order_accuracy == 0.0
    assert result.layout_iou == 0.0
    assert result.failures == ("reading_order_accuracy", "layout_iou")


def test_ocr_pdf_layout_extracts_word_boxes(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    import pymupdf

    pdf_path = tmp_path / "layout.pdf"
    document = pymupdf.open()
    document.new_page()
    document.new_page()
    document.save(pdf_path)
    document.close()

    calls = 0

    def fake_image_to_data(*args: object, **kwargs: object) -> dict[str, list[object]]:
        nonlocal calls
        calls += 1
        return {
            "text": ["", "Total", "zero-width", "42"],
            "left": [0, 10, 20, 80],
            "top": [0, 15, 15, 15],
            "width": [0, 50, 0, 20],
            "height": [0, 20, 20, 20],
        }

    monkeypatch.setattr("retos.evals.ocr.pytesseract.image_to_data", fake_image_to_data)

    assert ocr_pdf_layout(pdf_path, work_dir=tmp_path, max_pages=1) == (
        OCRLayoutBox(text="Total", x0=10, y0=15, x1=60, y1=35, page_number=1),
        OCRLayoutBox(text="42", x0=80, y0=15, x1=100, y1=35, page_number=1),
    )
    assert calls == 1


def test_ocr_quality_suite_can_generate_synthetic_cases(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("retos.evals.ocr.ocr_pdf_text", lambda raw, max_pages: "")

    report = run_ocr_quality_suite(work_dir=tmp_path)

    assert report.case_count == 2
    assert [case.case_id for case in report.cases] == [
        "typed-mission-brief",
        "typed-safety-note",
    ]
    assert (tmp_path / "typed-mission-brief.pdf").exists()
    assert (tmp_path / "typed-safety-note.pdf").exists()


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
    assert report.key_value_recall is None
    assert report.reading_order_accuracy is None
    assert report.layout_iou is None
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


def test_ocr_manifest_adapter_loads_cases_and_converts_image_inputs(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    from PIL import Image, ImageDraw

    image_path = tmp_path / "receipt.png"
    image = Image.new("RGB", (400, 160), "white")
    draw = ImageDraw.Draw(image)
    draw.text((24, 48), "Total due 42", fill="black")
    image.save(image_path)
    manifest_path = tmp_path / "ocr-manifest.json"
    manifest_path.write_text(
        """
        {
          "cases": [
            {
              "case_id": "receipt-total",
              "input_path": "receipt.png",
              "expected_text": "Total due 42",
              "expected_key_values": {"Total due": "42", "Ignored": "  "},
              "expected_layout": [
                {"text": "Total", "bbox": [24, 48, 74, 68], "page_number": 1},
                {"text": "42", "bbox": [96, 48, 116, 68]}
              ]
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    cases = load_ocr_benchmark_cases(manifest_path)

    seen_pdf = False

    def fake_ocr(raw: bytes, *, max_pages: int) -> str:
        nonlocal seen_pdf
        seen_pdf = raw.startswith(b"%PDF")
        return "Total due 42"

    def fake_layout(
        input_path: Path, *, work_dir: Path, max_pages: int
    ) -> tuple[OCRLayoutBox, ...]:
        assert input_path == image_path
        assert work_dir == tmp_path / "work"
        assert max_pages == 1
        return (
            OCRLayoutBox(text="Total", x0=24, y0=48, x1=74, y1=68),
            OCRLayoutBox(text="42", x0=96, y0=48, x1=116, y1=68),
        )

    monkeypatch.setattr("retos.evals.ocr.ocr_pdf_text", fake_ocr)
    monkeypatch.setattr("retos.evals.ocr.ocr_pdf_layout", fake_layout)
    report = run_ocr_quality_suite(
        work_dir=tmp_path / "work", suite_name="ocr-manifest", cases=cases
    )

    assert cases[0].case_id == "receipt-total"
    assert cases[0].input_path == image_path
    assert cases[0].expected_key_values == {"Total due": "42"}
    assert cases[0].expected_layout == (
        OCRLayoutBox(text="Total", x0=24, y0=48, x1=74, y1=68),
        OCRLayoutBox(text="42", x0=96, y0=48, x1=116, y1=68),
    )
    assert report.passed is True
    assert report.key_value_recall == 1.0
    assert report.reading_order_accuracy == 1.0
    assert report.layout_iou == 1.0
    assert "| Key-value recall | 1.0000 |" in report.to_markdown()
    assert "| Reading order accuracy | 1.0000 |" in report.to_markdown()
    assert "| Layout IoU | 1.0000 |" in report.to_markdown()
    assert seen_pdf is True


def test_ocr_manifest_adapter_rejects_invalid_key_value_shapes(tmp_path: Path) -> None:
    image_path = tmp_path / "case.pdf"
    write_image_only_pdf(image_path, "Total 42")
    manifest_path = tmp_path / "ocr-manifest.json"
    manifest_path.write_text(
        """
        {
          "cases": [
            {
              "case_id": "receipt-total",
              "input_path": "case.pdf",
              "expected_text": "Total 42",
              "expected_key_values": ["Total", "42"]
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    with pytest.raises(OCRBenchmarkAdapterError, match="expected_key_values"):
        load_ocr_benchmark_cases(manifest_path)

    manifest_path.write_text(
        """
        {
          "cases": [
            {
              "case_id": "receipt-total",
              "input_path": "case.pdf",
              "expected_text": "Total 42",
              "expected_key_values": {"Total": 42}
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    with pytest.raises(OCRBenchmarkAdapterError, match="keys and values"):
        load_ocr_benchmark_cases(manifest_path)


def test_ocr_manifest_adapter_rejects_invalid_layout_shapes(tmp_path: Path) -> None:
    image_path = tmp_path / "case.pdf"
    write_image_only_pdf(image_path, "Total 42")
    manifest_path = tmp_path / "ocr-manifest.json"
    manifest_path.write_text(
        """
        {
          "cases": [
            {
              "case_id": "receipt-total",
              "input_path": "case.pdf",
              "expected_text": "Total 42",
              "expected_layout": [{"text": "Total", "bbox": [0, 0, 0, 20]}]
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    with pytest.raises(OCRBenchmarkAdapterError, match="positive area"):
        load_ocr_benchmark_cases(manifest_path)

    manifest_path.write_text(
        """
        {
          "cases": [
            {
              "case_id": "receipt-total",
              "input_path": "case.pdf",
              "expected_text": "Total 42",
              "expected_layout": {"text": "Total", "bbox": [0, 0, 10, 20]}
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    with pytest.raises(OCRBenchmarkAdapterError, match="expected_layout"):
        load_ocr_benchmark_cases(manifest_path)

    manifest_path.write_text(
        """
        {
          "cases": [
            {
              "case_id": "receipt-total",
              "input_path": "case.pdf",
              "expected_text": "Total 42",
              "expected_layout": [42]
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    with pytest.raises(OCRBenchmarkAdapterError, match="expected_layout"):
        load_ocr_benchmark_cases(manifest_path)

    manifest_path.write_text(
        """
        {
          "cases": [
            {
              "case_id": "receipt-total",
              "input_path": "case.pdf",
              "expected_text": "Total 42",
              "expected_layout": [{"text": "Total", "bbox": [0, 0, "bad", 20]}]
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    with pytest.raises(OCRBenchmarkAdapterError, match="bbox values"):
        load_ocr_benchmark_cases(manifest_path)

    manifest_path.write_text(
        """
        {
          "cases": [
            {
              "case_id": "receipt-total",
              "input_path": "case.pdf",
              "expected_text": "Total 42",
              "expected_layout": [{"text": "Total", "bbox": [0, 0, 10, 20], "page_number": 0}]
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    with pytest.raises(OCRBenchmarkAdapterError, match="page_number"):
        load_ocr_benchmark_cases(manifest_path)


def test_ocr_funsd_adapter_reads_annotation_text(tmp_path: Path) -> None:
    dataset_root = tmp_path / "funsd"
    annotations = dataset_root / "annotations"
    images = dataset_root / "images"
    annotations.mkdir(parents=True)
    images.mkdir(parents=True)
    write_image_only_pdf(images / "form-1.pdf", "Name Alice total 42")
    (annotations / "form-1.json").write_text(
        json.dumps(
            {
                "form": [
                    {
                        "id": 1,
                        "label": "question",
                        "text": "Name",
                        "box": [0, 0, 40, 20],
                        "linking": [[1, 2]],
                    },
                    {
                        "id": 2,
                        "label": "answer",
                        "text": "Alice",
                        "box": [60, 0, 120, 20],
                        "linking": [[1, 2]],
                    },
                    {
                        "id": 3,
                        "label": "other",
                        "text": "total 42",
                        "box": [0, 40, 90, 60],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    cases = load_ocr_benchmark_cases(
        dataset_root,
        OCRBenchmarkOptions(dataset_format="funsd"),
    )

    assert cases == (
        OCRQualityCase(
            case_id="funsd-form-1",
            expected_text="Name Alice total 42",
            input_path=images / "form-1.pdf",
            expected_key_values={"Name": "Alice"},
            expected_layout=(
                OCRLayoutBox(text="Name", x0=0, y0=0, x1=40, y1=20),
                OCRLayoutBox(text="Alice", x0=60, y0=0, x1=120, y1=20),
                OCRLayoutBox(text="total 42", x0=0, y0=40, x1=90, y1=60),
            ),
        ),
    )


def test_ocr_funsd_adapter_ignores_unusable_key_value_links(tmp_path: Path) -> None:
    dataset_root = tmp_path / "funsd"
    annotations = dataset_root / "annotations"
    images = dataset_root / "images"
    annotations.mkdir(parents=True)
    images.mkdir(parents=True)
    write_image_only_pdf(images / "form-1.pdf", "Name Alice total 42")
    (annotations / "form-1.json").write_text(
        """
        {
          "form": [
            {"id": 1, "label": "question", "text": " ", "linking": [[1, 2]]},
            {"id": 2, "label": "question", "text": "Total", "linking": ["bad", [2, 99], [2, 3]]},
            {"id": 3, "label": "other", "text": "42"},
            {"id": 4, "label": "answer", "text": "unused"}
          ]
        }
        """,
        encoding="utf-8",
    )

    cases = load_ocr_benchmark_cases(
        dataset_root,
        OCRBenchmarkOptions(dataset_format="funsd"),
    )

    assert cases[0].expected_text == "Total 42 unused"
    assert cases[0].expected_key_values is None


def test_ocr_sroie_adapter_reads_box_text(tmp_path: Path) -> None:
    dataset_root = tmp_path / "sroie"
    box_root = dataset_root / "box"
    image_root = dataset_root / "img"
    entities_root = dataset_root / "entities"
    box_root.mkdir(parents=True)
    image_root.mkdir(parents=True)
    entities_root.mkdir(parents=True)
    write_image_only_pdf(image_root / "receipt-1.pdf", "STORE TOTAL 42")
    (box_root / "receipt-1.txt").write_text(
        "0,0,10,0,10,10,0,10,STORE\n0,20,10,20,10,30,0,30,TOTAL 42\n",
        encoding="utf-8",
    )
    (entities_root / "receipt-1.txt").write_text("company: STORE\ntotal: 42\n", encoding="utf-8")

    cases = load_ocr_benchmark_cases(
        dataset_root,
        OCRBenchmarkOptions(dataset_format="sroie"),
    )

    assert cases == (
        OCRQualityCase(
            case_id="sroie-receipt-1",
            expected_text="STORE TOTAL 42",
            input_path=image_root / "receipt-1.pdf",
            expected_key_values={"company": "STORE", "total": "42"},
            expected_layout=(
                OCRLayoutBox(text="STORE", x0=0, y0=0, x1=10, y1=10),
                OCRLayoutBox(text="TOTAL 42", x0=0, y0=20, x1=10, y1=30),
            ),
        ),
    )


def test_ocr_sroie_adapter_rejects_invalid_layout_coordinates(tmp_path: Path) -> None:
    dataset_root = tmp_path / "sroie"
    box_root = dataset_root / "box"
    image_root = dataset_root / "img"
    box_root.mkdir(parents=True)
    image_root.mkdir(parents=True)
    write_image_only_pdf(image_root / "receipt-1.pdf", "STORE")
    (box_root / "receipt-1.txt").write_text(
        "0,0,10,0,10,10,nope,10,STORE\n",
        encoding="utf-8",
    )

    with pytest.raises(OCRBenchmarkAdapterError, match="invalid coordinates"):
        load_ocr_benchmark_cases(
            dataset_root,
            OCRBenchmarkOptions(dataset_format="sroie"),
        )


def test_ocr_sroie_adapter_reads_json_entities_and_allows_missing_entities(
    tmp_path: Path,
) -> None:
    dataset_root = tmp_path / "sroie"
    box_root = dataset_root / "box"
    image_root = dataset_root / "img"
    entities_root = dataset_root / "entities"
    box_root.mkdir(parents=True)
    image_root.mkdir(parents=True)
    entities_root.mkdir(parents=True)
    write_image_only_pdf(image_root / "receipt-1.pdf", "STORE TOTAL 42")
    write_image_only_pdf(image_root / "receipt-2.pdf", "PLAIN TEXT")
    (box_root / "receipt-1.txt").write_text(
        "0,0,10,0,10,10,0,10,STORE\n0,20,10,20,10,30,0,30,TOTAL 42\n",
        encoding="utf-8",
    )
    (box_root / "receipt-2.txt").write_text(
        "0,0,10,0,10,10,0,10,PLAIN TEXT\n",
        encoding="utf-8",
    )
    (entities_root / "receipt-1.json").write_text(
        '{"company": "STORE", "total": "42", "empty": " "}',
        encoding="utf-8",
    )

    cases = load_ocr_benchmark_cases(
        dataset_root,
        OCRBenchmarkOptions(dataset_format="sroie"),
    )

    assert cases[0].expected_key_values == {"company": "STORE", "total": "42"}
    assert cases[1].expected_key_values is None


def test_ocr_sroie_adapter_rejects_invalid_json_entities(tmp_path: Path) -> None:
    dataset_root = tmp_path / "sroie"
    box_root = dataset_root / "box"
    image_root = dataset_root / "img"
    entities_root = dataset_root / "entities"
    box_root.mkdir(parents=True)
    image_root.mkdir(parents=True)
    entities_root.mkdir(parents=True)
    write_image_only_pdf(image_root / "receipt-1.pdf", "STORE")
    (box_root / "receipt-1.txt").write_text(
        "0,0,10,0,10,10,0,10,STORE\n",
        encoding="utf-8",
    )
    (entities_root / "receipt-1.json").write_text('["not", "object"]', encoding="utf-8")

    with pytest.raises(OCRBenchmarkAdapterError, match="must contain an object"):
        load_ocr_benchmark_cases(
            dataset_root,
            OCRBenchmarkOptions(dataset_format="sroie"),
        )


def test_ocr_benchmark_adapter_rejects_path_escape(tmp_path: Path) -> None:
    outside_pdf = tmp_path / "outside.pdf"
    write_image_only_pdf(outside_pdf, "outside")
    dataset_root = tmp_path / "dataset"
    dataset_root.mkdir()
    manifest_path = dataset_root / "manifest.json"
    manifest_path.write_text(
        """
        {
          "cases": [
            {
              "case_id": "escape",
              "input_path": "../outside.pdf",
              "expected_text": "outside"
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    with pytest.raises(OCRBenchmarkAdapterError, match="inside dataset root"):
        load_ocr_benchmark_cases(manifest_path)


def test_ocr_benchmark_adapter_rejects_invalid_options_and_manifest_shapes(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text('{"cases": []}', encoding="utf-8")

    with pytest.raises(OCRBenchmarkAdapterError, match="max_cases"):
        load_ocr_benchmark_cases(manifest_path, OCRBenchmarkOptions(max_cases=0))

    with pytest.raises(OCRBenchmarkAdapterError, match="Unsupported"):
        load_ocr_benchmark_cases(
            manifest_path,
            OCRBenchmarkOptions(dataset_format="unknown"),
        )

    manifest_path.write_text('{"cases": {}}', encoding="utf-8")
    with pytest.raises(OCRBenchmarkAdapterError, match="cases list"):
        load_ocr_benchmark_cases(manifest_path)

    manifest_path.write_text('{"cases": [42]}', encoding="utf-8")
    with pytest.raises(OCRBenchmarkAdapterError, match=r"cases\[0\]"):
        load_ocr_benchmark_cases(manifest_path)

    manifest_path.write_text(
        '{"cases": [{"case_id": "missing-text", "input_path": "case.pdf"}]}',
        encoding="utf-8",
    )
    with pytest.raises(OCRBenchmarkAdapterError, match="expected_text"):
        load_ocr_benchmark_cases(manifest_path)

    manifest_path.write_text(
        (
            '{"cases": [{"case_id": "missing-file", "expected_text": "x", '
            '"input_path": "missing.pdf"}]}'
        ),
        encoding="utf-8",
    )
    with pytest.raises(OCRBenchmarkAdapterError, match="input file not found"):
        load_ocr_benchmark_cases(manifest_path)


def test_ocr_benchmark_adapter_rejects_invalid_json(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(OCRBenchmarkAdapterError, match="not valid JSON"):
        load_ocr_benchmark_cases(manifest_path)


def test_funsd_adapter_rejects_invalid_dataset_shapes(tmp_path: Path) -> None:
    dataset_root = tmp_path / "funsd"

    with pytest.raises(OCRBenchmarkAdapterError, match="annotations directory"):
        load_ocr_benchmark_cases(
            dataset_root,
            OCRBenchmarkOptions(dataset_format="funsd"),
        )

    annotations = dataset_root / "annotations"
    annotations.mkdir(parents=True)
    (annotations / "bad-form.json").write_text('{"form": {}}', encoding="utf-8")
    with pytest.raises(OCRBenchmarkAdapterError, match="missing form list"):
        load_ocr_benchmark_cases(
            dataset_root,
            OCRBenchmarkOptions(dataset_format="funsd"),
        )

    (annotations / "bad-form.json").unlink()
    (annotations / "empty-form.json").write_text('{"form": [{"text": "  "}]}', encoding="utf-8")
    with pytest.raises(OCRBenchmarkAdapterError, match="has no text"):
        load_ocr_benchmark_cases(
            dataset_root,
            OCRBenchmarkOptions(dataset_format="funsd"),
        )

    (annotations / "empty-form.json").unlink()
    (annotations / "missing-image.json").write_text(
        '{"form": [{"text": "Name Alice"}]}',
        encoding="utf-8",
    )
    (dataset_root / "images").mkdir()
    with pytest.raises(OCRBenchmarkAdapterError, match="Could not find benchmark image"):
        load_ocr_benchmark_cases(
            dataset_root,
            OCRBenchmarkOptions(dataset_format="funsd"),
        )


def test_sroie_adapter_rejects_invalid_dataset_shapes(tmp_path: Path) -> None:
    dataset_root = tmp_path / "sroie"
    dataset_root.mkdir()

    with pytest.raises(OCRBenchmarkAdapterError, match="missing one of these directories"):
        load_ocr_benchmark_cases(
            dataset_root,
            OCRBenchmarkOptions(dataset_format="sroie"),
        )

    box_root = dataset_root / "box"
    image_root = dataset_root / "img"
    box_root.mkdir()
    image_root.mkdir()
    (box_root / "empty.txt").write_text("", encoding="utf-8")
    with pytest.raises(OCRBenchmarkAdapterError, match="has no text"):
        load_ocr_benchmark_cases(
            dataset_root,
            OCRBenchmarkOptions(dataset_format="sroie"),
        )

    (box_root / "empty.txt").unlink()
    (box_root / "missing-image.txt").write_text(
        "0,0,10,0,10,10,0,10,TOTAL\n",
        encoding="utf-8",
    )
    with pytest.raises(OCRBenchmarkAdapterError, match="Could not find benchmark image"):
        load_ocr_benchmark_cases(
            dataset_root,
            OCRBenchmarkOptions(dataset_format="sroie"),
        )
