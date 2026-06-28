import gzip
import json
from pathlib import Path

import pytest

from retos.evals.agent import run_agent_multihop_eval_suite
from retos.evals.datasets import (
    DatasetAdapterError,
    HotpotQAAdapterOptions,
    NaturalQuestionsAdapterOptions,
    SquadAdapterOptions,
    load_hotpotqa_agent_cases,
    load_hotpotqa_cases,
    load_natural_questions_cases,
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


def write_hotpotqa_fixture(path: Path) -> Path:
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
                                "the United States Air Force.",
                                "They monitored nuclear test-ban compliance.",
                            ],
                        ],
                        [
                            "United States Air Force",
                            [
                                "The United States Air Force is a military service branch.",
                                "Its history includes operating satellite programs.",
                            ],
                        ],
                        [
                            "Unrelated astronomy",
                            ["A telescope catalog mentions stars and nebulae."],
                        ],
                    ],
                },
                {
                    "_id": "apollo-lunar",
                    "question": "Which program carried astronauts to the lunar surface?",
                    "answer": "Apollo program",
                    "supporting_facts": [["Apollo program", 0]],
                    "context": [
                        [
                            "Apollo program",
                            [
                                "The Apollo program carried astronauts to the lunar surface.",
                            ],
                        ]
                    ],
                },
            ]
        ),
        encoding="utf-8",
    )
    return path


def write_natural_questions_fixture(path: Path) -> Path:
    items = [
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
        },
        {
            "example_id": 456,
            "question_text": "Who invented the ocean on Mercury?",
            "document_title": "Mercury (planet)",
            "document_text": "Mercury is a rocky planet without liquid oceans.",
            "annotations": [
                {
                    "long_answer": {"start_token": -1, "end_token": -1},
                    "short_answers": [],
                    "yes_no_answer": "NONE",
                }
            ],
        },
    ]
    path.write_text("\n".join(json.dumps(item) for item in items), encoding="utf-8")
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


def test_hotpotqa_adapter_maps_multi_hop_cases(tmp_path: Path) -> None:
    dataset_path = write_hotpotqa_fixture(tmp_path / "hotpot.json")

    cases = load_hotpotqa_cases(dataset_path)

    assert [case.id for case in cases] == [
        "hotpotqa-vela-air-force",
        "hotpotqa-apollo-lunar",
    ]
    case = cases[0]
    assert case.question.startswith("Which agency operated Vela")
    assert case.expected_answer_terms == ("United States Air Force",)
    assert case.expected_citation_titles == (
        "HotpotQA: United States Air Force",
        "HotpotQA: Vela",
    )
    assert [document.title for document in case.documents] == [
        "HotpotQA: Vela",
        "HotpotQA: United States Air Force",
        "HotpotQA: Unrelated astronomy",
    ]
    assert case.documents[0].anchor == "hotpotqa://hotpot.json#vela-air-force/vela"


def test_hotpotqa_agent_adapter_maps_supporting_facts_to_agent_cases(
    tmp_path: Path,
) -> None:
    dataset_path = write_hotpotqa_fixture(tmp_path / "hotpot.json")

    cases = load_hotpotqa_agent_cases(dataset_path)

    assert [case.id for case in cases] == ["hotpotqa-agent-vela-air-force"]
    case = cases[0]
    assert case.question.startswith(
        "Compare HotpotQA supporting facts for United States Air Force and Vela"
    )
    assert case.expected_answer_terms == ("United States Air Force",)
    assert case.expected_citation_titles == (
        "HotpotQA: United States Air Force",
        "HotpotQA: Vela",
    )
    assert set(case.expected_bridge_terms).issuperset({"force", "states", "united"})
    assert case.max_evidence_tokens == 256
    assert [document.title for document in case.documents] == [
        "HotpotQA: Vela",
        "HotpotQA: United States Air Force",
    ]


def test_natural_questions_adapter_maps_jsonl_answerable_and_unanswerable_cases(
    tmp_path: Path,
) -> None:
    dataset_path = write_natural_questions_fixture(tmp_path / "nq.jsonl")

    cases = load_natural_questions_cases(dataset_path)

    assert [case.id for case in cases] == [
        "natural-questions-123",
        "natural-questions-456",
    ]
    answerable = cases[0]
    assert answerable.question == "Which star is Mercury closest to?"
    assert answerable.expected_answer_terms == ("Sun",)
    assert answerable.expected_citation_titles == ("Natural Questions: Mercury (planet)",)
    assert answerable.documents[0].anchor == "natural-questions://nq.jsonl#123"

    unanswerable = cases[1]
    assert unanswerable.expect_abstention is True
    assert unanswerable.documents == ()
    assert unanswerable.expected_answer_terms == ()


def test_natural_questions_adapter_accepts_document_tokens_and_respects_max_cases(
    tmp_path: Path,
) -> None:
    dataset_path = tmp_path / "nq-object.json"
    dataset_path.write_text(
        json.dumps(
            {
                "data": [
                    {
                        "example_id": "token-case",
                        "question_text": "Which craft landed at Tranquility Base?",
                        "document_url": "https://en.wikipedia.org/wiki/Apollo_11",
                        "document_tokens": [
                            {"token": "<P>", "html_token": True},
                            {"token": "Apollo", "html_token": False},
                            {"token": "11", "html_token": False},
                            {"token": "landed", "html_token": False},
                            {"token": "at", "html_token": False},
                            {"token": "Tranquility", "html_token": False},
                            {"token": "Base", "html_token": False},
                        ],
                        "annotations": [
                            {
                                "long_answer": {"start_token": 1, "end_token": 7},
                                "short_answers": [{"start_token": 1, "end_token": 3}],
                                "yes_no_answer": "NONE",
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    cases = load_natural_questions_cases(
        dataset_path,
        NaturalQuestionsAdapterOptions(max_cases=1),
    )

    assert len(cases) == 1
    assert cases[0].documents[0].text == "Apollo 11 landed at Tranquility Base"
    assert cases[0].expected_answer_terms == ("Apollo 11",)
    assert cases[0].expected_citation_titles == ("Natural Questions: Apollo_11",)


def test_natural_questions_cases_run_through_local_eval_harness(tmp_path: Path) -> None:
    dataset_path = write_natural_questions_fixture(tmp_path / "nq.jsonl")
    cases = load_natural_questions_cases(dataset_path)

    report = run_smoke_eval_suite(
        index_root=tmp_path / "index",
        suite_name="natural-questions-fixture",
        cases=cases,
    )

    assert report.passed is True
    assert report.case_count == 2
    assert report.retrieval_recall == 1.0
    assert report.abstention == 1.0


def test_natural_questions_adapter_can_exclude_unanswerable_cases(tmp_path: Path) -> None:
    dataset_path = write_natural_questions_fixture(tmp_path / "nq.jsonl")

    cases = load_natural_questions_cases(
        dataset_path,
        NaturalQuestionsAdapterOptions(include_unanswerable=False),
    )

    assert [case.id for case in cases] == ["natural-questions-123"]


def test_natural_questions_adapter_accepts_gzipped_jsonl(tmp_path: Path) -> None:
    source_path = write_natural_questions_fixture(tmp_path / "nq.jsonl")
    gz_path = tmp_path / "nq.jsonl.gz"
    with gzip.open(gz_path, "wt", encoding="utf-8") as handle:
        handle.write(source_path.read_text(encoding="utf-8"))

    cases = load_natural_questions_cases(gz_path, NaturalQuestionsAdapterOptions(max_cases=1))

    assert cases[0].id == "natural-questions-123"
    assert cases[0].documents[0].anchor == "natural-questions://nq.jsonl.gz#123"


def test_natural_questions_adapter_skips_yes_no_answer_terms(tmp_path: Path) -> None:
    dataset_path = tmp_path / "nq-yes.json"
    dataset_path.write_text(
        json.dumps(
            {
                "example_id": "yes-case",
                "question_text": "Is Mercury closest to the Sun?",
                "document_title": "Mercury",
                "document_text": "Mercury is closest to the Sun.",
                "annotations": [
                    {
                        "long_answer": {"start_token": 0, "end_token": 6},
                        "short_answers": [],
                        "yes_no_answer": "YES",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    cases = load_natural_questions_cases(dataset_path)

    assert cases[0].expected_answer_terms == ()


def test_natural_questions_adapter_rejects_invalid_tokens(tmp_path: Path) -> None:
    dataset_path = tmp_path / "nq-bad-token.json"
    dataset_path.write_text(
        json.dumps(
            {
                "example_id": "bad-token",
                "question_text": "What is malformed?",
                "document_tokens": [{"html_token": False}],
                "annotations": [
                    {
                        "long_answer": {"start_token": 0, "end_token": 1},
                        "short_answers": [],
                        "yes_no_answer": "NONE",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(DatasetAdapterError, match="document_tokens\\[0\\]\\.token"):
        load_natural_questions_cases(dataset_path)


def test_natural_questions_adapter_rejects_non_object_token(tmp_path: Path) -> None:
    dataset_path = tmp_path / "nq-bad-token-item.json"
    dataset_path.write_text(
        json.dumps(
            {
                "example_id": "bad-token-item",
                "question_text": "What is malformed?",
                "document_tokens": [123],
                "annotations": [
                    {
                        "long_answer": {"start_token": 0, "end_token": 1},
                        "short_answers": [],
                        "yes_no_answer": "NONE",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(DatasetAdapterError, match="document_tokens\\[0\\]"):
        load_natural_questions_cases(dataset_path)


def test_natural_questions_adapter_rejects_missing_document_text(tmp_path: Path) -> None:
    dataset_path = tmp_path / "nq-missing-document.json"
    dataset_path.write_text(
        json.dumps(
            {
                "example_id": "missing-document",
                "question_text": "What is missing?",
                "annotations": [
                    {
                        "long_answer": {"start_token": 0, "end_token": 1},
                        "short_answers": [],
                        "yes_no_answer": "NONE",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(DatasetAdapterError, match="document_text or document_tokens"):
        load_natural_questions_cases(dataset_path)


def test_natural_questions_adapter_rejects_invalid_long_answer(tmp_path: Path) -> None:
    dataset_path = tmp_path / "nq-bad-long-answer.json"
    dataset_path.write_text(
        json.dumps(
            {
                "example_id": "bad-long",
                "question_text": "What is malformed?",
                "document_text": "A small document.",
                "annotations": [{"long_answer": None, "short_answers": []}],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(DatasetAdapterError, match="invalid long_answer"):
        load_natural_questions_cases(dataset_path)


def test_natural_questions_adapter_rejects_empty_long_answer(tmp_path: Path) -> None:
    dataset_path = tmp_path / "nq-empty-long-answer.json"
    dataset_path.write_text(
        json.dumps(
            {
                "example_id": "empty-long",
                "question_text": "What is empty?",
                "document_tokens": [{"token": "<P>", "html_token": True}],
                "annotations": [
                    {
                        "long_answer": {"start_token": 0, "end_token": 1},
                        "short_answers": [],
                        "yes_no_answer": "NONE",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(DatasetAdapterError, match="empty long answer"):
        load_natural_questions_cases(dataset_path)


def test_natural_questions_adapter_rejects_non_object_short_answers(tmp_path: Path) -> None:
    dataset_path = tmp_path / "nq-bad-short.json"
    dataset_path.write_text(
        json.dumps(
            {
                "example_id": "bad-short",
                "question_text": "What is malformed?",
                "document_text": "Mercury is close to the Sun.",
                "annotations": [
                    {
                        "long_answer": {"start_token": 0, "end_token": 6},
                        "short_answers": ["bad"],
                        "yes_no_answer": "NONE",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(DatasetAdapterError, match="short_answers items"):
        load_natural_questions_cases(dataset_path)


def test_natural_questions_adapter_rejects_missing_annotations(tmp_path: Path) -> None:
    dataset_path = tmp_path / "nq-missing-annotations.json"
    dataset_path.write_text(
        json.dumps(
            {
                "example_id": "missing-annotations",
                "question_text": "What is missing?",
                "document_text": "A document exists.",
                "annotations": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(DatasetAdapterError, match="must include annotations"):
        load_natural_questions_cases(dataset_path)


def test_natural_questions_adapter_rejects_malformed_wrapped_items(tmp_path: Path) -> None:
    dataset_path = tmp_path / "nq-wrapped.json"
    dataset_path.write_text(json.dumps({"data": ["bad"]}), encoding="utf-8")

    with pytest.raises(DatasetAdapterError, match="Expected every Natural Questions item"):
        load_natural_questions_cases(dataset_path)


def test_natural_questions_adapter_rejects_missing_file_and_empty_file(tmp_path: Path) -> None:
    with pytest.raises(DatasetAdapterError, match="Could not read dataset file"):
        load_natural_questions_cases(tmp_path / "missing-nq.jsonl")

    empty_path = tmp_path / "empty-nq.jsonl"
    empty_path.write_text("", encoding="utf-8")
    with pytest.raises(DatasetAdapterError, match="Dataset file is empty"):
        load_natural_questions_cases(empty_path)


def test_natural_questions_adapter_rejects_invalid_json_object(tmp_path: Path) -> None:
    dataset_path = tmp_path / "bad-nq.json"
    dataset_path.write_text("{", encoding="utf-8")

    with pytest.raises(DatasetAdapterError, match="not valid JSON"):
        load_natural_questions_cases(dataset_path)


def test_natural_questions_adapter_rejects_non_object_jsonl_line(tmp_path: Path) -> None:
    dataset_path = tmp_path / "bad-line-nq.jsonl"
    dataset_path.write_text("[]", encoding="utf-8")

    with pytest.raises(DatasetAdapterError, match="line 1 to be an object"):
        load_natural_questions_cases(dataset_path)


def test_natural_questions_adapter_rejects_invalid_jsonl(tmp_path: Path) -> None:
    dataset_path = tmp_path / "bad-nq.jsonl"
    dataset_path.write_text('{"example_id": 1}\n{', encoding="utf-8")

    with pytest.raises(DatasetAdapterError, match="JSONL line 2"):
        load_natural_questions_cases(dataset_path)


def test_hotpotqa_adapter_respects_max_cases(tmp_path: Path) -> None:
    dataset_path = write_hotpotqa_fixture(tmp_path / "hotpot.json")

    cases = load_hotpotqa_cases(dataset_path, HotpotQAAdapterOptions(max_cases=1))

    assert len(cases) == 1
    assert cases[0].id == "hotpotqa-vela-air-force"


def test_hotpotqa_adapter_accepts_object_root_and_skips_yes_no_terms(tmp_path: Path) -> None:
    dataset_path = tmp_path / "hotpot-object.json"
    dataset_path.write_text(
        json.dumps(
            {
                "data": [
                    {
                        "_id": "yes-no-case",
                        "question": "Was Vela operated by the United States Air Force?",
                        "answer": "yes",
                        "supporting_facts": [["Vela", 0]],
                        "context": [
                            [
                                "Vela",
                                [
                                    "Vela spacecraft were satellites operated by "
                                    "the United States Air Force."
                                ],
                            ]
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    cases = load_hotpotqa_cases(dataset_path)

    assert cases[0].expected_answer_terms == ()


def test_hotpotqa_adapter_rejects_bad_supporting_facts(tmp_path: Path) -> None:
    dataset_path = tmp_path / "hotpot-bad-support.json"
    dataset_path.write_text(
        json.dumps(
            [
                {
                    "_id": "bad-support",
                    "question": "What is malformed?",
                    "answer": "malformed",
                    "supporting_facts": [],
                    "context": [["Doc", ["Text"]]],
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(DatasetAdapterError, match="must include supporting facts"):
        load_hotpotqa_cases(dataset_path)


def test_hotpotqa_adapter_rejects_empty_context_text(tmp_path: Path) -> None:
    dataset_path = tmp_path / "hotpot-empty-context.json"
    dataset_path.write_text(
        json.dumps(
            [
                {
                    "_id": "empty-context",
                    "question": "What is empty?",
                    "answer": "empty",
                    "supporting_facts": [["Doc", 0]],
                    "context": [["Doc", ["   "]]],
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(DatasetAdapterError, match="has no text"):
        load_hotpotqa_cases(dataset_path)


def test_hotpotqa_cases_run_through_local_eval_harness(tmp_path: Path) -> None:
    dataset_path = write_hotpotqa_fixture(tmp_path / "hotpot.json")
    cases = load_hotpotqa_cases(dataset_path, HotpotQAAdapterOptions(max_cases=1))

    report = run_smoke_eval_suite(
        index_root=tmp_path / "index",
        suite_name="hotpotqa-fixture",
        cases=cases,
    )

    assert report.passed is True
    assert report.case_count == 1
    assert report.retrieval_recall == 1.0
    assert report.grounded_answer == 1.0


def test_hotpotqa_agent_cases_run_through_agent_audit_harness(tmp_path: Path) -> None:
    dataset_path = write_hotpotqa_fixture(tmp_path / "hotpot.json")
    cases = load_hotpotqa_agent_cases(dataset_path, HotpotQAAdapterOptions(max_cases=1))

    report = run_agent_multihop_eval_suite(
        index_root=tmp_path / "agent-index",
        suite_name="hotpotqa-agent-fixture",
        cases=cases,
    )

    assert report.passed is True
    assert report.case_count == 1
    assert report.query_plan == 1.0
    assert report.multi_hop_support == 1.0
    assert report.evidence_route == 1.0
    assert report.grounded_answer == 1.0


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


def test_hotpotqa_adapter_rejects_missing_supporting_context(tmp_path: Path) -> None:
    dataset_path = tmp_path / "bad-hotpot.json"
    dataset_path.write_text(
        json.dumps(
            [
                {
                    "_id": "broken",
                    "question": "What is broken?",
                    "answer": "missing",
                    "supporting_facts": [["Missing title", 0]],
                    "context": [["Present title", ["Present text."]]],
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(DatasetAdapterError, match="missing supporting context"):
        load_hotpotqa_cases(dataset_path)


def test_hotpotqa_adapter_rejects_malformed_context(tmp_path: Path) -> None:
    dataset_path = tmp_path / "bad-context.json"
    dataset_path.write_text(
        json.dumps(
            [
                {
                    "_id": "broken",
                    "question": "What is broken?",
                    "answer": "bad context",
                    "supporting_facts": [["Broken", 0]],
                    "context": [{"title": "Broken", "sentences": ["Bad shape"]}],
                }
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(DatasetAdapterError, match=r"context\[0\]"):
        load_hotpotqa_cases(dataset_path)


def test_hotpotqa_adapter_rejects_non_object_array_items(tmp_path: Path) -> None:
    dataset_path = tmp_path / "bad-root.json"
    dataset_path.write_text(json.dumps(["bad"]), encoding="utf-8")

    with pytest.raises(DatasetAdapterError, match="every HotpotQA case"):
        load_hotpotqa_cases(dataset_path)
