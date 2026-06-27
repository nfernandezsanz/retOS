from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from retos.evals.smoke import EvalCase, EvalDocument


class DatasetAdapterError(ValueError):
    pass


@dataclass(frozen=True)
class SquadAdapterOptions:
    max_cases: int | None = None
    include_answerable: bool = True
    include_unanswerable: bool = True


def load_squad_v2_cases(
    dataset_path: Path,
    options: SquadAdapterOptions | None = None,
) -> tuple[EvalCase, ...]:
    adapter_options = options or SquadAdapterOptions()
    payload = read_json_object(dataset_path)
    version = payload.get("version")
    if version is not None and not str(version).startswith("v2"):
        raise DatasetAdapterError(f"Expected SQuAD v2 dataset, got version {version!r}")

    cases: list[EvalCase] = []
    for article in require_list(payload, "data"):
        title = require_string(article, "title")
        for paragraph in require_list(article, "paragraphs"):
            context = require_string(paragraph, "context")
            for question_answer in require_list(paragraph, "qas"):
                case = case_from_squad_qa(
                    dataset_name=dataset_path.name,
                    title=title,
                    context=context,
                    question_answer=question_answer,
                    options=adapter_options,
                )
                if case is None:
                    continue
                cases.append(case)
                if (
                    adapter_options.max_cases is not None
                    and len(cases) >= adapter_options.max_cases
                ):
                    return tuple(cases)
    return tuple(cases)


def case_from_squad_qa(
    *,
    dataset_name: str,
    title: str,
    context: str,
    question_answer: dict[str, Any],
    options: SquadAdapterOptions,
) -> EvalCase | None:
    question_id = require_string(question_answer, "id")
    question = require_string(question_answer, "question")
    is_impossible = bool(question_answer.get("is_impossible", False))

    if is_impossible:
        if not options.include_unanswerable:
            return None
        return EvalCase(
            id=f"squad-{slugify(question_id)}",
            question=question,
            documents=(),
            expected_citation_titles=(),
            expected_answer_terms=(),
            expect_abstention=True,
        )

    if not options.include_answerable:
        return None

    answers = require_list(question_answer, "answers")
    if not answers:
        raise DatasetAdapterError(f"Answerable SQuAD question {question_id!r} has no answers")
    answer_text = require_string(answers[0], "text")
    document_title = f"SQuAD: {title}"
    return EvalCase(
        id=f"squad-{slugify(question_id)}",
        question=question,
        documents=(
            EvalDocument(
                id=f"squad-{slugify(question_id)}-context",
                title=document_title,
                text=context,
                anchor=f"squad://{dataset_name}#{question_id}",
            ),
        ),
        expected_citation_titles=(document_title,),
        expected_answer_terms=(answer_text,),
        expect_abstention=False,
    )


def read_json_object(dataset_path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise DatasetAdapterError(f"Could not read dataset file: {dataset_path}") from exc
    except json.JSONDecodeError as exc:
        raise DatasetAdapterError(f"Dataset file is not valid JSON: {dataset_path}") from exc
    if not isinstance(payload, dict):
        raise DatasetAdapterError("Dataset root must be a JSON object")
    return payload


def require_list(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise DatasetAdapterError(f"Expected {key!r} to be a list")
    if not all(isinstance(item, dict) for item in value):
        raise DatasetAdapterError(f"Expected every item in {key!r} to be an object")
    return value


def require_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DatasetAdapterError(f"Expected {key!r} to be a non-empty string")
    return value.strip()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip()).strip("-").lower()
    return slug[:80] or "case"
