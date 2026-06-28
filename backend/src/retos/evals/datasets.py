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


@dataclass(frozen=True)
class HotpotQAAdapterOptions:
    max_cases: int | None = None


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


def load_hotpotqa_cases(
    dataset_path: Path,
    options: HotpotQAAdapterOptions | None = None,
) -> tuple[EvalCase, ...]:
    adapter_options = options or HotpotQAAdapterOptions()
    payload = read_json_value(dataset_path)
    if isinstance(payload, dict):
        raw_cases = require_list(payload, "data")
    elif isinstance(payload, list):
        if not all(isinstance(item, dict) for item in payload):
            raise DatasetAdapterError("Expected every HotpotQA case to be an object")
        raw_cases = payload
    else:
        raise DatasetAdapterError("HotpotQA dataset root must be a JSON array or object")

    cases: list[EvalCase] = []
    for raw_case in raw_cases:
        cases.append(case_from_hotpotqa_item(dataset_name=dataset_path.name, item=raw_case))
        if adapter_options.max_cases is not None and len(cases) >= adapter_options.max_cases:
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


def case_from_hotpotqa_item(*, dataset_name: str, item: dict[str, Any]) -> EvalCase:
    case_id = require_string(item, "_id")
    question = require_string(item, "question")
    answer = require_string(item, "answer")
    supporting_titles = supporting_fact_titles(item)
    documents = hotpotqa_documents(
        dataset_name=dataset_name,
        case_id=case_id,
        context=require_raw_list(item, "context"),
    )
    available_titles = {document.title.removeprefix("HotpotQA: ") for document in documents}
    missing_support = sorted(supporting_titles - available_titles)
    if missing_support:
        raise DatasetAdapterError(
            f"HotpotQA case {case_id!r} references missing supporting context: "
            f"{', '.join(missing_support)}"
        )

    normalized_answer = answer.strip().lower()
    answer_terms = () if normalized_answer in {"yes", "no", "noanswer"} else (answer,)
    return EvalCase(
        id=f"hotpotqa-{slugify(case_id)}",
        question=question,
        documents=documents,
        expected_citation_titles=tuple(f"HotpotQA: {title}" for title in sorted(supporting_titles)),
        expected_answer_terms=answer_terms,
        expect_abstention=False,
    )


def supporting_fact_titles(item: dict[str, Any]) -> set[str]:
    titles: set[str] = set()
    for index, fact in enumerate(require_raw_list(item, "supporting_facts")):
        if (
            not isinstance(fact, list | tuple)
            or len(fact) < 2
            or not isinstance(fact[0], str)
            or not fact[0].strip()
        ):
            raise DatasetAdapterError(
                f"Expected HotpotQA supporting_facts[{index}] to be [title, sentence_id]"
            )
        titles.add(fact[0].strip())
    if not titles:
        raise DatasetAdapterError("HotpotQA case must include supporting facts")
    return titles


def hotpotqa_documents(
    *,
    dataset_name: str,
    case_id: str,
    context: list[Any],
) -> tuple[EvalDocument, ...]:
    documents: list[EvalDocument] = []
    for index, entry in enumerate(context):
        if (
            not isinstance(entry, list | tuple)
            or len(entry) != 2
            or not isinstance(entry[0], str)
            or not entry[0].strip()
            or not isinstance(entry[1], list)
            or not all(isinstance(sentence, str) for sentence in entry[1])
        ):
            raise DatasetAdapterError(
                f"Expected HotpotQA context[{index}] to be [title, [sentences]]"
            )
        title = entry[0].strip()
        text = " ".join(sentence.strip() for sentence in entry[1] if sentence.strip())
        if not text:
            raise DatasetAdapterError(f"HotpotQA context {title!r} has no text")
        documents.append(
            EvalDocument(
                id=f"hotpotqa-{slugify(case_id)}-{slugify(title)}",
                title=f"HotpotQA: {title}",
                text=text,
                anchor=f"hotpotqa://{dataset_name}#{case_id}/{slugify(title)}",
            )
        )
    return tuple(documents)


def read_json_object(dataset_path: Path) -> dict[str, Any]:
    payload = read_json_value(dataset_path)
    if not isinstance(payload, dict):
        raise DatasetAdapterError("Dataset root must be a JSON object")
    return payload


def read_json_value(dataset_path: Path) -> Any:
    try:
        payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise DatasetAdapterError(f"Could not read dataset file: {dataset_path}") from exc
    except json.JSONDecodeError as exc:
        raise DatasetAdapterError(f"Dataset file is not valid JSON: {dataset_path}") from exc
    return payload


def require_list(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise DatasetAdapterError(f"Expected {key!r} to be a list")
    if not all(isinstance(item, dict) for item in value):
        raise DatasetAdapterError(f"Expected every item in {key!r} to be an object")
    return value


def require_raw_list(payload: dict[str, Any], key: str) -> list[Any]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise DatasetAdapterError(f"Expected {key!r} to be a list")
    return value


def require_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DatasetAdapterError(f"Expected {key!r} to be a non-empty string")
    return value.strip()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip()).strip("-").lower()
    return slug[:80] or "case"
