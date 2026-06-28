from dataclasses import dataclass

from retos.agent.audits import (
    audit_contradictions,
    audit_evidence,
    audit_evidence_route,
    audit_multi_hop,
    ensure_evidence_ledger,
    plan_query,
    query_plan_to_payload,
)


@dataclass(frozen=True)
class FixtureCitation:
    segment_id: str
    text: str
    document_id: str = "document-1"
    title: str = "Fixture Document"
    anchor: str | None = "page=1"


@dataclass(frozen=True)
class FixtureNeighborContext:
    segment_id: str
    source_segment_id: str


def test_evidence_audit_marks_uncited_answers() -> None:
    citation = FixtureCitation("segment-known", "Known evidence")

    audit = audit_evidence("Answer without the id.", [citation])

    assert audit.grounded is False
    assert audit.cited_segment_ids == []
    assert audit.unreferenced_citation_ids == ["segment-known"]


def test_evidence_ledger_links_uncited_answers() -> None:
    citation = FixtureCitation("segment-known", "Known evidence")

    answer, audit = ensure_evidence_ledger("Answer without ids.", [citation])

    assert "Evidence ledger: segment-known" in answer
    assert audit.grounded is True
    assert audit.cited_segment_ids == ["segment-known"]


def test_contradiction_audit_flags_opposite_polarity_citations() -> None:
    positive = FixtureCitation(
        "segment-positive",
        "Apollo checklist validation confirmed guidance readiness.",
    )
    negative = FixtureCitation(
        "segment-negative",
        "Apollo checklist validation did not confirm guidance readiness.",
    )

    audit = audit_contradictions([positive, negative])

    assert audit.checked is True
    assert audit.conflict_count == 1
    assert audit.findings[0].segment_ids == ["segment-positive", "segment-negative"]
    assert {"apollo", "checklist", "validation", "confirm", "guidance", "readiness"}.issuperset(
        set(audit.findings[0].shared_terms)
    )


def test_evidence_route_flags_single_document_evidence_with_context() -> None:
    citation = FixtureCitation(
        "segment-known",
        "Known evidence",
        document_id="document-a",
        title="Mission Notes",
        anchor="page=7",
    )
    neighbor = FixtureNeighborContext(
        segment_id="segment-neighbor",
        source_segment_id="segment-known",
    )

    route = audit_evidence_route([citation], [neighbor])

    assert route.coverage_level == "single_segment"
    assert route.segment_count == 1
    assert route.document_count == 1
    assert route.anchor_count == 1
    assert route.multi_document is False
    assert route.has_neighbor_context is True
    assert route.warnings == ["single_citation", "single_document"]
    assert route.documents[0].title == "Mission Notes"
    assert route.documents[0].segment_ids == ["segment-known"]
    assert route.documents[0].anchors == ["page=7"]


def test_evidence_route_recognizes_multi_document_coverage() -> None:
    left = FixtureCitation(
        "segment-left",
        "Left evidence",
        document_id="document-a",
        title="Mission Notes",
        anchor="page=1",
    )
    right = FixtureCitation(
        "segment-right",
        "Right evidence",
        document_id="document-b",
        title="Review Notes",
        anchor="page=3",
    )

    route = audit_evidence_route([left, right])

    assert route.coverage_level == "multi_document"
    assert route.document_count == 2
    assert route.anchor_count == 2
    assert route.multi_document is True
    assert route.warnings == ["no_neighbor_context"]


def test_multi_hop_audit_flags_single_document_multi_hop_question() -> None:
    citation = FixtureCitation(
        "segment-one",
        "Apollo reviews mention checklist evidence.",
        document_id="document-a",
    )

    audit = audit_multi_hop("Compare Apollo reviews and checklist evidence", [citation])

    assert audit.checked is True
    assert audit.requires_multi_hop is True
    assert audit.status == "insufficient_multi_document_evidence"
    assert audit.document_count == 1
    assert audit.bridge_terms == []
    assert audit.warnings == ["multi_hop_question_single_document"]


def test_multi_hop_audit_recognizes_cross_document_bridge_terms() -> None:
    left = FixtureCitation(
        "segment-left",
        "Apollo checklist review confirmed guidance readiness.",
        document_id="document-a",
    )
    right = FixtureCitation(
        "segment-right",
        "Mission checklist review compared guidance telemetry.",
        document_id="document-b",
    )

    audit = audit_multi_hop("Compare Apollo checklist review and telemetry", [left, right])

    assert audit.requires_multi_hop is True
    assert audit.status == "supported_multi_document"
    assert audit.document_count == 2
    assert {"checklist", "review", "guidance"}.issuperset(set(audit.bridge_terms))
    assert audit.warnings == []


def test_query_plan_splits_multi_hop_questions_into_searches() -> None:
    plan = plan_query("Compare Apollo checklist review and telemetry readiness")

    assert plan.strategy == "multi_hop_evidence_route"
    assert plan.requires_multi_hop is True
    assert plan.expected_evidence == "multi_document"
    assert plan.search_queries[0] == "Compare Apollo checklist review and telemetry readiness"
    assert "apollo checklist review" in plan.search_queries
    assert "readiness telemetry" in plan.search_queries
    assert [step.name for step in plan.steps] == ["search", "read", "route", "audit"]
    assert query_plan_to_payload(plan)["strategy"] == "multi_hop_evidence_route"


def test_query_plan_warns_on_low_specificity_questions() -> None:
    plan = plan_query("Why?")

    assert plan.strategy == "direct_evidence_lookup"
    assert plan.requires_multi_hop is False
    assert plan.warnings == ["low_specificity_question"]
