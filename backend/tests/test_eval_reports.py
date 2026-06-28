import json
from dataclasses import dataclass
from pathlib import Path

from retos.evals.reports import sanitize_report_stem, write_report_files


@dataclass(frozen=True)
class DummyWritableReport:
    suite_name: str = "suite/name with spaces"

    def to_dict(self) -> dict[str, object]:
        return {"suite_name": self.suite_name, "passed": True}

    def to_markdown(self) -> str:
        return f"# {self.suite_name}\n"


def test_sanitize_report_stem_keeps_safe_characters() -> None:
    assert sanitize_report_stem("SQuAD v2: run #1 / domain_a") == "SQuAD-v2-run-1-domain_a"


def test_sanitize_report_stem_falls_back_for_empty_values() -> None:
    assert sanitize_report_stem(" __--- / | \n ") == "eval-report"


def test_sanitize_report_stem_limits_long_names() -> None:
    assert sanitize_report_stem("x" * 140) == "x" * 120


def test_write_report_files_uses_sanitized_explicit_stem(tmp_path: Path) -> None:
    report = DummyWritableReport()

    json_path, markdown_path = write_report_files(
        report=report,
        report_dir=tmp_path / "nested" / "reports",
        report_stem="unsafe/name | run",
    )

    assert json_path == tmp_path / "nested" / "reports" / "unsafe-name-run.json"
    assert markdown_path == tmp_path / "nested" / "reports" / "unsafe-name-run.md"
    assert json.loads(json_path.read_text(encoding="utf-8")) == {
        "passed": True,
        "suite_name": "suite/name with spaces",
    }
    assert markdown_path.read_text(encoding="utf-8") == "# suite/name with spaces\n"


def test_write_report_files_falls_back_to_suite_name(tmp_path: Path) -> None:
    json_path, markdown_path = write_report_files(
        report=DummyWritableReport(suite_name="agent:multi hop"),
        report_dir=tmp_path,
        report_stem=None,
    )

    assert json_path.name == "agent-multi-hop.json"
    assert markdown_path.name == "agent-multi-hop.md"
