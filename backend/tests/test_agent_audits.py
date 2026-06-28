from dataclasses import dataclass

from retos.agent.audits import audit_contradictions, audit_evidence, ensure_evidence_ledger


@dataclass(frozen=True)
class FixtureCitation:
    segment_id: str
    text: str


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
