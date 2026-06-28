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
    assert "# Eval Report: squad-v2" in markdown_report.read_text(encoding="utf-8")


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


def test_eval_cli_requires_dataset_path_for_squad(tmp_path: Path, capsys) -> None:
    cli = load_eval_cli()

    exit_code = cli.run(
        index_root=tmp_path / "index",
        output_format="markdown",
        suite="squad",
        dataset_path=None,
        max_cases=1,
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--dataset-path is required" in captured.err


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
