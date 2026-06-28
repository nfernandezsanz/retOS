from pathlib import Path

from retos.evals.agent import agent_multihop_eval_cases, run_agent_multihop_eval_suite
from retos.evals.smoke import (
    EvalCase,
    EvalDocument,
    run_smoke_eval_suite,
    score_case,
    smoke_eval_cases,
)
from retos.search.index import SearchHit


def test_smoke_eval_suite_passes_with_local_index(tmp_path: Path) -> None:
    report = run_smoke_eval_suite(index_root=tmp_path)

    assert report.passed is True
    assert report.case_count == 3
    assert report.retrieval_recall == 1.0
    assert report.citation_validity == 1.0
    assert report.grounded_answer == 1.0
    assert report.abstention == 1.0
    assert report.budget_compliance == 1.0
    assert report.to_dict()["metrics"]["retrieval_recall"] == 1.0
    assert report.to_dict()["metadata"] == {}
    assert "Eval Report: retos-smoke" in report.to_markdown()


def test_eval_report_includes_metadata_in_json_and_markdown(tmp_path: Path) -> None:
    report = run_smoke_eval_suite(
        index_root=tmp_path,
        metadata={
            "dataset_path": "/datasets/squad.json",
            "adapter": "squad-v2",
        },
    )

    payload = report.to_dict()
    markdown = report.to_markdown()

    assert payload["metadata"] == {
        "dataset_path": "/datasets/squad.json",
        "adapter": "squad-v2",
    }
    assert "| Metadata | Value |" in markdown
    assert "| adapter | squad-v2 |" in markdown
    assert "| dataset_path | /datasets/squad.json |" in markdown


def test_smoke_eval_cases_are_immutable_fixtures() -> None:
    cases = smoke_eval_cases()

    assert [case.id for case in cases] == [
        "apollo-guidance",
        "marine-salinity",
        "no-evidence",
    ]
    assert all(case.max_citations == 5 for case in cases)


def test_agent_multihop_eval_suite_validates_plan_audits_and_budget(tmp_path: Path) -> None:
    report = run_agent_multihop_eval_suite(
        index_root=tmp_path,
        metadata={"dataset": "agent-multihop-fixtures"},
    )

    assert report.passed is True
    assert report.case_count == 1
    assert report.query_plan == 1.0
    assert report.multi_hop_support == 1.0
    assert report.evidence_route == 1.0
    assert report.citation_validity == 1.0
    assert report.grounded_answer == 1.0
    assert report.budget_compliance == 1.0
    payload = report.to_dict()
    assert payload["metrics"]["multi_hop_support"] == 1.0
    assert payload["cases"][0]["usage"]["search_count"] >= 2
    assert payload["cases"][0]["audits"]["query_plan"]["strategy"] == "multi_hop_evidence_route"
    markdown = report.to_markdown()
    assert "Agent Eval Report: agent-multihop" in markdown
    assert markdown.index("| Budget compliance | 1.00 |") < markdown.index("| Metadata | Value |")
    assert markdown.index("| Metadata | Value |") < markdown.index("| Case | Status | Failures |")


def test_agent_multihop_eval_cases_are_immutable_fixtures() -> None:
    cases = agent_multihop_eval_cases()

    assert [case.id for case in cases] == ["apollo-telemetry-bridge"]
    assert cases[0].min_search_count == 2


def test_eval_case_reports_missing_grounding() -> None:
    case = EvalCase(
        id="grounding",
        question="What does the fixture mention?",
        documents=(
            EvalDocument(
                id="fixture",
                title="Fixture",
                text="The fixture mentions deterministic evidence.",
                anchor="fixture://grounding#p1",
            ),
        ),
        expected_citation_titles=("Fixture",),
        expected_answer_terms=("missing answer term",),
    )
    hits = [
        SearchHit(
            segment_id="grounding-fixture-segment-0",
            document_id="grounding-fixture",
            document_version_id="grounding-fixture-v1",
            title="Fixture",
            text="The fixture mentions deterministic evidence.",
            anchor="fixture://grounding#p1",
            ordinal=0,
            score=1.0,
        )
    ]

    result = score_case(case, hits, "Grounded answer without the expected phrase.")

    assert result.passed is False
    assert result.retrieval_recall is True
    assert result.citation_validity is True
    assert result.grounded_answer is False
    assert result.failures == ("grounded_answer",)
