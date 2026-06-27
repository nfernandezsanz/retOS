import json
from pathlib import Path

import pytest

from retos.evals.datasets import (
    DatasetAdapterError,
    SquadAdapterOptions,
    load_squad_v2_cases,
)
from retos.evals.smoke import run_smoke_eval_suite


def write_squad_fixture(path: Path) -> Path:
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
                                            {
                                                "text": "iron oxide dust",
                                                "answer_start": 39,
                                            }
                                        ],
                                        "is_impossible": False,
                                    },
                                    {
                                        "id": "mars-ocean-depth",
                                        "question": "How deep are the oceans on Mars today?",
                                        "answers": [],
                                        "plausible_answers": [],
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


def test_squad_v2_adapter_maps_answerable_and_unanswerable_cases(tmp_path: Path) -> None:
    dataset_path = write_squad_fixture(tmp_path / "squad.json")

    cases = load_squad_v2_cases(dataset_path)

    assert [case.id for case in cases] == [
        "squad-mars-red-planet",
        "squad-mars-ocean-depth",
    ]
    answerable = cases[0]
    assert answerable.question == "Why is Mars called the Red Planet?"
    assert answerable.expected_answer_terms == ("iron oxide dust",)
    assert answerable.expected_citation_titles == ("SQuAD: Solar System",)
    assert answerable.documents[0].anchor == "squad://squad.json#mars-red-planet"

    unanswerable = cases[1]
    assert unanswerable.expect_abstention is True
    assert unanswerable.documents == ()
    assert unanswerable.expected_answer_terms == ()


def test_squad_v2_adapter_respects_max_cases(tmp_path: Path) -> None:
    dataset_path = write_squad_fixture(tmp_path / "squad.json")

    cases = load_squad_v2_cases(dataset_path, SquadAdapterOptions(max_cases=1))

    assert len(cases) == 1
    assert cases[0].id == "squad-mars-red-planet"


def test_squad_v2_adapter_can_exclude_unanswerable_cases(tmp_path: Path) -> None:
    dataset_path = write_squad_fixture(tmp_path / "squad.json")

    cases = load_squad_v2_cases(
        dataset_path,
        SquadAdapterOptions(include_unanswerable=False),
    )

    assert [case.id for case in cases] == ["squad-mars-red-planet"]


def test_squad_v2_adapter_can_exclude_answerable_cases(tmp_path: Path) -> None:
    dataset_path = write_squad_fixture(tmp_path / "squad.json")

    cases = load_squad_v2_cases(
        dataset_path,
        SquadAdapterOptions(include_answerable=False),
    )

    assert [case.id for case in cases] == ["squad-mars-ocean-depth"]


def test_squad_v2_cases_run_through_local_eval_harness(tmp_path: Path) -> None:
    dataset_path = write_squad_fixture(tmp_path / "squad.json")
    cases = load_squad_v2_cases(dataset_path)

    report = run_smoke_eval_suite(
        index_root=tmp_path / "index",
        suite_name="squad-v2-fixture",
        cases=cases,
    )

    assert report.passed is True
    assert report.case_count == 2
    assert report.retrieval_recall == 1.0
    assert report.abstention == 1.0


def test_squad_v2_adapter_rejects_wrong_version(tmp_path: Path) -> None:
    dataset_path = tmp_path / "squad-v1.json"
    dataset_path.write_text(json.dumps({"version": "1.1", "data": []}), encoding="utf-8")

    with pytest.raises(DatasetAdapterError, match="Expected SQuAD v2"):
        load_squad_v2_cases(dataset_path)


def test_squad_v2_adapter_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(DatasetAdapterError, match="Could not read dataset file"):
        load_squad_v2_cases(tmp_path / "missing.json")


def test_squad_v2_adapter_rejects_invalid_json(tmp_path: Path) -> None:
    dataset_path = tmp_path / "invalid.json"
    dataset_path.write_text("{", encoding="utf-8")

    with pytest.raises(DatasetAdapterError, match="not valid JSON"):
        load_squad_v2_cases(dataset_path)


def test_squad_v2_adapter_rejects_non_object_root(tmp_path: Path) -> None:
    dataset_path = tmp_path / "array.json"
    dataset_path.write_text("[]", encoding="utf-8")

    with pytest.raises(DatasetAdapterError, match="root must be a JSON object"):
        load_squad_v2_cases(dataset_path)


def test_squad_v2_adapter_rejects_malformed_lists(tmp_path: Path) -> None:
    dataset_path = tmp_path / "bad-data.json"
    dataset_path.write_text(json.dumps({"version": "v2.0", "data": {}}), encoding="utf-8")

    with pytest.raises(DatasetAdapterError, match="Expected 'data' to be a list"):
        load_squad_v2_cases(dataset_path)


def test_squad_v2_adapter_rejects_non_object_list_items(tmp_path: Path) -> None:
    dataset_path = tmp_path / "bad-data-item.json"
    dataset_path.write_text(json.dumps({"version": "v2.0", "data": ["bad"]}), encoding="utf-8")

    with pytest.raises(DatasetAdapterError, match="every item in 'data' to be an object"):
        load_squad_v2_cases(dataset_path)


def test_squad_v2_adapter_rejects_blank_strings(tmp_path: Path) -> None:
    dataset_path = tmp_path / "blank-title.json"
    dataset_path.write_text(
        json.dumps({"version": "v2.0", "data": [{"title": "", "paragraphs": []}]}),
        encoding="utf-8",
    )

    with pytest.raises(DatasetAdapterError, match="'title' to be a non-empty string"):
        load_squad_v2_cases(dataset_path)


def test_squad_v2_adapter_rejects_answerable_question_without_answers(tmp_path: Path) -> None:
    dataset_path = tmp_path / "bad-squad.json"
    dataset_path.write_text(
        json.dumps(
            {
                "version": "v2.0",
                "data": [
                    {
                        "title": "Broken",
                        "paragraphs": [
                            {
                                "context": "Broken context",
                                "qas": [
                                    {
                                        "id": "broken",
                                        "question": "What broke?",
                                        "answers": [],
                                        "is_impossible": False,
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(DatasetAdapterError, match="has no answers"):
        load_squad_v2_cases(dataset_path)
