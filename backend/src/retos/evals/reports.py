from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol


class EvalReportWritable(Protocol):
    @property
    def suite_name(self) -> str: ...

    def to_dict(self) -> dict[str, object]: ...

    def to_markdown(self) -> str: ...


def write_report_files(
    *,
    report: EvalReportWritable,
    report_dir: Path,
    report_stem: str | None,
) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    stem = sanitize_report_stem(report_stem or report.suite_name)
    json_path = report_dir / f"{stem}.json"
    markdown_path = report_dir / f"{stem}.md"
    json_path.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(report.to_markdown(), encoding="utf-8")
    return json_path, markdown_path


def sanitize_report_stem(value: str) -> str:
    stem = "".join(
        character if character.isalnum() or character in ("-", "_") else "-" for character in value
    )
    stem = "-".join(part for part in stem.strip("-_").split("-") if part)
    return stem[:120] or "eval-report"
