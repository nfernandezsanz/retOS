import importlib.util
import json
from pathlib import Path
from types import ModuleType


def load_eval_cli() -> ModuleType:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_eval_smoke.py"
    spec = importlib.util.spec_from_file_location("run_eval_smoke", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load eval CLI from {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_squad_cli_fixture(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "version": "v2.0",
                "data": [
                    {
                        "title": "Solar System",
                        "paragraphs": [
                            {
                                "context": (
                                    "Mars is called the Red Planet because iron oxide dust "
                                    "covers much of its surface."
                                ),
                                "qas": [
                                    {
                                        "id": "mars-red-planet",
                                        "question": "Why is Mars called the Red Planet?",
                                        "answers": [
                                            {"text": "iron oxide dust", "answer_start": 39}
                                        ],
                                        "is_impossible": False,
                                    },
                                    {
                                        "id": "mars-ocean-depth",
                                        "question": "How deep are the oceans on Mars today?",
                                        "answers": [],
                                        "is_impossible": True,
                                    },
                                ],
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def write_hotpotqa_cli_fixture(path: Path) -> Path:
    path.write_text(
        json.dumps(
            [
                {
                    "_id": "vela-air-force",
                    "question": (
                        "Which agency operated Vela spacecraft in the United States "
                        "Air Force history?"
                    ),
                    "answer": "United States Air Force",
                    "supporting_facts": [["Vela", 0], ["United States Air Force", 0]],
                    "context": [
                        [
                            "Vela",
                            [
                                "Vela spacecraft were satellites operated by "
                                "the United States Air Force."
                            ],
                        ],
                        [
                            "United States Air Force",
                            ["The United States Air Force operated satellite programs."],
                        ],
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    return path


def write_natural_questions_cli_fixture(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "example_id": 123,
                "question_text": "Which star is Mercury closest to?",
                "document_title": "Mercury (planet)",
                "document_text": (
                    "Mercury is the closest planet to the Sun and has a short orbital year."
                ),
                "annotations": [
                    {
                        "long_answer": {"start_token": 0, "end_token": 14},
                        "short_answers": [{"start_token": 7, "end_token": 8}],
                        "yes_no_answer": "NONE",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_eval_cli_runs_squad_suite_from_local_file(tmp_path: Path, capsys) -> None:
    dataset_path = write_squad_cli_fixture(tmp_path / "squad.json")
    cli = load_eval_cli()

    exit_code = cli.run(
        index_root=tmp_path / "index",
        output_format="json",
        suite="squad",
        dataset_path=dataset_path,
        max_cases=2,
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"suite_name": "squad-v2"' in captured.out
    assert '"case_count": 2' in captured.out
    assert '"adapter": "squad-v2"' in captured.out
    assert f'"dataset_path": "{dataset_path}"' in captured.out


def test_eval_cli_runs_hotpotqa_suite_from_local_file(tmp_path: Path, capsys) -> None:
    dataset_path = write_hotpotqa_cli_fixture(tmp_path / "hotpot.json")
    cli = load_eval_cli()

    exit_code = cli.run(
        index_root=tmp_path / "index",
        output_format="json",
        suite="hotpotqa",
        dataset_path=dataset_path,
        max_cases=1,
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"suite_name": "hotpotqa"' in captured.out
    assert '"case_count": 1' in captured.out


def test_eval_cli_runs_natural_questions_suite_from_local_file(
    tmp_path: Path,
    capsys,
) -> None:
    dataset_path = write_natural_questions_cli_fixture(tmp_path / "nq.jsonl")
    cli = load_eval_cli()

    exit_code = cli.run(
        index_root=tmp_path / "index",
        output_format="json",
        suite="natural-questions",
        dataset_path=dataset_path,
        max_cases=1,
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"suite_name": "natural-questions"' in captured.out
    assert '"case_count": 1' in captured.out


def test_eval_cli_writes_json_and_markdown_reports(tmp_path: Path, capsys) -> None:
    dataset_path = write_squad_cli_fixture(tmp_path / "squad.json")
    report_dir = tmp_path / "reports"
    cli = load_eval_cli()

    exit_code = cli.run(
        index_root=tmp_path / "index",
        output_format="markdown",
        suite="squad",
        dataset_path=dataset_path,
        max_cases=2,
        report_dir=report_dir,
        report_stem="nightly/squad v2",
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Wrote eval reports:" in captured.err
    json_report = report_dir / "nightly-squad-v2.json"
    markdown_report = report_dir / "nightly-squad-v2.md"
    assert json_report.exists()
    assert markdown_report.exists()
    assert json.loads(json_report.read_text(encoding="utf-8"))["suite_name"] == "squad-v2"
    report_payload = json.loads(json_report.read_text(encoding="utf-8"))
    assert report_payload["metadata"]["adapter"] == "squad-v2"
    markdown = markdown_report.read_text(encoding="utf-8")
    assert "# Eval Report: squad-v2" in markdown
    assert "| adapter | squad-v2 |" in markdown


def test_eval_cli_uses_suite_name_as_default_report_stem(tmp_path: Path) -> None:
    cli = load_eval_cli()

    exit_code = cli.run(
        index_root=tmp_path / "index",
        output_format="json",
        suite="smoke",
        dataset_path=None,
        max_cases=None,
        report_dir=tmp_path / "reports",
    )

    assert exit_code == 0
    assert (tmp_path / "reports" / "retos-smoke.json").exists()
    assert (tmp_path / "reports" / "retos-smoke.md").exists()


def test_eval_cli_runs_agent_multihop_suite(tmp_path: Path, capsys) -> None:
    cli = load_eval_cli()

    exit_code = cli.run(
        index_root=tmp_path / "index",
        output_format="json",
        suite="agent-multihop",
        dataset_path=None,
        max_cases=None,
        report_dir=tmp_path / "reports",
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"suite_name": "agent-multihop"' in captured.out
    assert '"multi_hop_support": 1.0' in captured.out
    assert (tmp_path / "reports" / "agent-multihop.json").exists()
    assert (tmp_path / "reports" / "agent-multihop.md").exists()


def test_eval_cli_runs_ocr_smoke_suite(tmp_path: Path, capsys, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    cli = load_eval_cli()

    def fake_ocr_suite(*, work_dir: Path):
        from retos.evals.ocr import OCRQualityCase, run_ocr_quality_suite

        monkeypatch.setattr("retos.evals.ocr.ocr_pdf_text", lambda raw, max_pages: "OCR text")
        return run_ocr_quality_suite(
            work_dir=work_dir,
            cases=(OCRQualityCase(case_id="ocr", expected_text="OCR text"),),
        )

    monkeypatch.setattr(cli, "run_ocr_quality_suite", fake_ocr_suite)

    exit_code = cli.run(
        index_root=tmp_path / "index",
        output_format="markdown",
        suite="ocr-smoke",
        dataset_path=None,
        max_cases=None,
        report_dir=tmp_path / "reports",
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "OCR Quality Report: ocr-smoke" in captured.out
    assert (tmp_path / "reports" / "ocr-smoke.json").exists()
    assert (tmp_path / "reports" / "ocr-smoke.md").exists()


def test_eval_cli_runs_ocr_benchmark_suite_from_manifest(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    from retos.evals.ocr import write_image_only_pdf

    dataset_root = tmp_path / "ocr-dataset"
    dataset_root.mkdir()
    write_image_only_pdf(dataset_root / "case.pdf", "Invoice total 42")
    manifest_path = dataset_root / "manifest.json"
    manifest_path.write_text(
        """
        {
          "cases": [
            {
              "case_id": "invoice",
              "input_path": "case.pdf",
              "expected_text": "Invoice total 42"
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    monkeypatch.setattr("retos.evals.ocr.ocr_pdf_text", lambda raw, max_pages: "Invoice total 42")
    cli = load_eval_cli()

    exit_code = cli.run(
        index_root=tmp_path / "index",
        output_format="markdown",
        suite="ocr-benchmark",
        dataset_path=manifest_path,
        max_cases=1,
        dataset_format="manifest",
        report_dir=tmp_path / "reports",
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "OCR Quality Report: ocr-manifest" in captured.out
    assert (tmp_path / "reports" / "ocr-manifest.json").exists()


def test_eval_cli_reports_missing_tesseract_for_ocr_suite(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    from pytesseract import TesseractNotFoundError

    cli = load_eval_cli()

    def missing_tesseract(*, work_dir: Path):
        raise TesseractNotFoundError()

    monkeypatch.setattr(cli, "run_ocr_quality_suite", missing_tesseract)

    exit_code = cli.run(
        index_root=tmp_path / "index",
        output_format="markdown",
        suite="ocr-smoke",
        dataset_path=None,
        max_cases=None,
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "tesseract is required" in captured.err


def test_eval_cli_requires_dataset_path_for_dataset_suites(tmp_path: Path, capsys) -> None:
    cli = load_eval_cli()

    exit_code = cli.run(
        index_root=tmp_path / "index",
        output_format="markdown",
        suite="hotpotqa",
        dataset_path=None,
        max_cases=1,
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--dataset-path is required for dataset-backed suites" in captured.err


def test_eval_cli_rejects_non_positive_max_cases(tmp_path: Path, capsys) -> None:
    dataset_path = write_squad_cli_fixture(tmp_path / "squad.json")
    cli = load_eval_cli()

    exit_code = cli.run(
        index_root=tmp_path / "index",
        output_format="markdown",
        suite="squad",
        dataset_path=dataset_path,
        max_cases=0,
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--max-cases must be greater than zero" in captured.err
