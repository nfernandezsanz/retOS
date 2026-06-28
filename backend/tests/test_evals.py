from pathlib import Path

from retos.evals.agent import agent_multihop_eval_cases, run_agent_multihop_eval_suite
from retos.evals.smoke import (
    EvalCase,
    EvalDocument,
    run_smoke_eval_suite,
    score_case,
    search_eval_evidence,
    smoke_eval_cases,
)
from retos.search.index import IndexedSegment, SearchHit, TantivySearchIndex


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
    assert report.case_count == 3
    assert report.query_plan == 1.0
    assert report.multi_hop_support == 1.0
    assert report.evidence_route == 1.0
    assert report.citation_validity == 1.0
    assert report.grounded_answer == 1.0
    assert report.budget_compliance == 1.0
    payload = report.to_dict()
    assert payload["metrics"]["multi_hop_support"] == 1.0
    assert {case["case_id"] for case in payload["cases"]} == {
        "apollo-telemetry-bridge",
        "incident-escalation-triage",
        "invoice-retention-policy",
    }
    for case in payload["cases"]:
        assert case["usage"]["search_count"] >= 2
        assert case["audits"]["query_plan"]["strategy"] == "multi_hop_evidence_route"
    strict_budget_case = next(
        case for case in payload["cases"] if case["case_id"] == "incident-escalation-triage"
    )
    assert strict_budget_case["usage"]["citation_count"] == 2
    assert strict_budget_case["usage"]["within_budget"] is True
    markdown = report.to_markdown()
    assert "Agent Eval Report: agent-multihop" in markdown
    assert markdown.index("| Budget compliance | 1.00 |") < markdown.index("| Metadata | Value |")
    assert markdown.index("| Metadata | Value |") < markdown.index("| Case | Status | Failures |")


def test_agent_multihop_eval_cases_are_immutable_fixtures() -> None:
    cases = agent_multihop_eval_cases()

    assert [case.id for case in cases] == [
        "apollo-telemetry-bridge",
        "invoice-retention-policy",
        "incident-escalation-triage",
    ]
    assert cases[0].min_search_count == 2
    assert cases[2].max_citations == 2


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


def test_eval_search_uses_named_entity_followups_for_multihop_cases(tmp_path: Path) -> None:
    case = EvalCase(
        id="hotpot-style",
        question=("What government position was held by the woman who portrayed Corliss Archer?"),
        documents=(
            EvalDocument(
                id="kiss",
                title="HotpotQA: Kiss and Tell",
                text="Kiss and Tell starred Shirley Temple as Corliss Archer.",
                anchor="fixture://hotpot/kiss",
            ),
            EvalDocument(
                id="shirley",
                title="HotpotQA: Shirley Temple",
                text="Shirley Temple served as Chief of Protocol of the United States.",
                anchor="fixture://hotpot/shirley",
            ),
            EvalDocument(
                id="noise",
                title="HotpotQA: Other Film",
                text="Other Film discussed unrelated casting notes.",
                anchor="fixture://hotpot/noise",
            ),
        ),
        expected_citation_titles=("HotpotQA: Kiss and Tell", "HotpotQA: Shirley Temple"),
        expected_answer_terms=("Chief of Protocol",),
        max_citations=2,
    )
    index = TantivySearchIndex(tmp_path / "index")
    index.rebuild_domain(
        "domain",
        [
            IndexedSegment(
                segment_id=f"{document.id}-segment",
                document_id=document.id,
                document_version_id=f"{document.id}-v1",
                title=document.title,
                text=document.text,
                anchor=document.anchor,
                ordinal=ordinal,
            )
            for ordinal, document in enumerate(case.documents)
        ],
    )

    hits = search_eval_evidence(index=index, domain_id="domain", case=case)

    assert {hit.title for hit in hits} >= {
        "HotpotQA: Kiss and Tell",
        "HotpotQA: Shirley Temple",
    }
