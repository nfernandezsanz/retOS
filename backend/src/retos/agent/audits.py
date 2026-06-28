from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


class AuditedCitation(Protocol):
    @property
    def segment_id(self) -> str: ...

    @property
    def document_id(self) -> str: ...

    @property
    def title(self) -> str: ...

    @property
    def anchor(self) -> str | None: ...

    @property
    def text(self) -> str: ...


class AuditedNeighborContext(Protocol):
    @property
    def segment_id(self) -> str: ...

    @property
    def source_segment_id(self) -> str: ...


@dataclass(frozen=True)
class EvidenceAudit:
    grounded: bool
    cited_segment_ids: list[str]
    unreferenced_citation_ids: list[str]


@dataclass(frozen=True)
class ContradictionFinding:
    segment_ids: list[str]
    shared_terms: list[str]
    summary: str


@dataclass(frozen=True)
class ContradictionAudit:
    checked: bool
    conflict_count: int
    findings: list[ContradictionFinding]


@dataclass(frozen=True)
class MultiHopAudit:
    checked: bool
    requires_multi_hop: bool
    status: str
    document_count: int
    bridge_terms: list[str]
    warnings: list[str]


@dataclass(frozen=True)
class EvidenceRouteDocument:
    document_id: str
    title: str
    segment_ids: list[str]
    anchors: list[str]


@dataclass(frozen=True)
class EvidenceRoute:
    coverage_level: str
    segment_count: int
    document_count: int
    anchor_count: int
    multi_document: bool
    has_neighbor_context: bool
    documents: list[EvidenceRouteDocument]
    warnings: list[str]


NEGATION_TERMS = frozenset({"no", "not", "never", "without", "absent", "false", "failed"})
MULTI_HOP_MARKERS = frozenset(
    {
        "after",
        "and",
        "between",
        "both",
        "compare",
        "compared",
        "connection",
        "difference",
        "during",
        "earlier",
        "later",
        "relationship",
        "same",
        "versus",
        "while",
    }
)
STOPWORDS = frozenset(
    {
        "about",
        "after",
        "again",
        "against",
        "before",
        "being",
        "between",
        "could",
        "every",
        "found",
        "from",
        "should",
        "their",
        "there",
        "these",
        "those",
        "through",
        "using",
        "were",
        "which",
        "with",
        "would",
    }
)


def audit_evidence(answer: str, citations: Sequence[AuditedCitation]) -> EvidenceAudit:
    citation_ids = [citation.segment_id for citation in citations]
    cited_ids = [segment_id for segment_id in citation_ids if segment_id in answer]
    unreferenced_ids = [segment_id for segment_id in citation_ids if segment_id not in cited_ids]
    return EvidenceAudit(
        grounded=not citations or bool(cited_ids),
        cited_segment_ids=cited_ids,
        unreferenced_citation_ids=unreferenced_ids,
    )


def ensure_evidence_ledger(
    answer: str,
    citations: Sequence[AuditedCitation],
) -> tuple[str, EvidenceAudit]:
    audit = audit_evidence(answer, citations)
    if audit.grounded or not citations:
        return answer, audit
    ledger = ", ".join(citation.segment_id for citation in citations)
    updated_answer = f"{answer.rstrip()}\n\nEvidence ledger: {ledger}"
    return updated_answer, audit_evidence(updated_answer, citations)


def significant_terms(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", value.lower())
        if len(token) >= 5 and token not in STOPWORDS and token not in NEGATION_TERMS
    }


def has_negation(value: str) -> bool:
    tokens = set(re.findall(r"[a-z0-9]+", value.lower()))
    return bool(tokens & NEGATION_TERMS)


def audit_contradictions(citations: Sequence[AuditedCitation]) -> ContradictionAudit:
    findings: list[ContradictionFinding] = []
    for left_index, left in enumerate(citations):
        left_terms = significant_terms(left.text)
        if not left_terms:
            continue
        left_negative = has_negation(left.text)
        for right in citations[left_index + 1 :]:
            right_negative = has_negation(right.text)
            if left_negative == right_negative:
                continue
            shared_terms = sorted(left_terms & significant_terms(right.text))
            if len(shared_terms) < 2:
                continue
            findings.append(
                ContradictionFinding(
                    segment_ids=[left.segment_id, right.segment_id],
                    shared_terms=shared_terms[:6],
                    summary=(
                        "Potential contradiction: cited segments share terms with "
                        "opposite polarity markers."
                    ),
                )
            )
    return ContradictionAudit(
        checked=True,
        conflict_count=len(findings),
        findings=findings,
    )


def audit_multi_hop(question: str, citations: Sequence[AuditedCitation]) -> MultiHopAudit:
    question_tokens = set(re.findall(r"[a-z0-9]+", question.lower()))
    requires_multi_hop = bool(question_tokens & MULTI_HOP_MARKERS)
    document_ids = {citation.document_id for citation in citations}
    document_count = len(document_ids)
    bridge_terms = cross_document_bridge_terms(citations)

    warnings: list[str] = []
    if not citations:
        status = "no_evidence"
        if requires_multi_hop:
            warnings.append("multi_hop_question_without_evidence")
    elif requires_multi_hop and document_count < 2:
        status = "insufficient_multi_document_evidence"
        warnings.append("multi_hop_question_single_document")
    elif requires_multi_hop and not bridge_terms:
        status = "multi_document_without_bridge_terms"
        warnings.append("missing_cross_document_bridge_terms")
    elif requires_multi_hop:
        status = "supported_multi_document"
    elif document_count > 1 and bridge_terms:
        status = "opportunistic_multi_document"
    else:
        status = "not_required"

    return MultiHopAudit(
        checked=True,
        requires_multi_hop=requires_multi_hop,
        status=status,
        document_count=document_count,
        bridge_terms=bridge_terms,
        warnings=warnings,
    )


def cross_document_bridge_terms(citations: Sequence[AuditedCitation]) -> list[str]:
    terms_by_document: dict[str, set[str]] = {}
    for citation in citations:
        terms_by_document.setdefault(citation.document_id, set()).update(
            significant_terms(citation.text)
        )
    if len(terms_by_document) < 2:
        return []

    document_terms = list(terms_by_document.values())
    bridge_terms = set(document_terms[0])
    for terms in document_terms[1:]:
        bridge_terms &= terms
    return sorted(bridge_terms)[:12]


def audit_evidence_route(
    citations: Sequence[AuditedCitation],
    neighbor_context: Sequence[AuditedNeighborContext] = (),
) -> EvidenceRoute:
    documents: dict[str, EvidenceRouteDocument] = {}
    anchors: set[str] = set()
    for citation in citations:
        route_document = documents.setdefault(
            citation.document_id,
            EvidenceRouteDocument(
                document_id=citation.document_id,
                title=citation.title,
                segment_ids=[],
                anchors=[],
            ),
        )
        route_document.segment_ids.append(citation.segment_id)
        if citation.anchor:
            route_document.anchors.append(citation.anchor)
            anchors.add(f"{citation.document_id}:{citation.anchor}")

    document_list = sorted(
        documents.values(),
        key=lambda document: (-len(document.segment_ids), document.title, document.document_id),
    )
    segment_count = len(citations)
    document_count = len(document_list)
    has_neighbor_context = bool(neighbor_context)
    if segment_count == 0:
        coverage_level = "no_evidence"
    elif segment_count == 1:
        coverage_level = "single_segment"
    elif document_count == 1:
        coverage_level = "single_document"
    else:
        coverage_level = "multi_document"

    warnings: list[str] = []
    if segment_count == 0:
        warnings.append("no_citations")
    elif segment_count == 1:
        warnings.append("single_citation")
    if segment_count > 0 and document_count == 1:
        warnings.append("single_document")
    if segment_count > 0 and not has_neighbor_context:
        warnings.append("no_neighbor_context")

    return EvidenceRoute(
        coverage_level=coverage_level,
        segment_count=segment_count,
        document_count=document_count,
        anchor_count=len(anchors),
        multi_document=document_count > 1,
        has_neighbor_context=has_neighbor_context,
        documents=document_list,
        warnings=warnings,
    )


def evidence_audit_to_payload(audit: EvidenceAudit) -> dict[str, object]:
    return {
        "grounded": audit.grounded,
        "cited_segment_ids": audit.cited_segment_ids,
        "unreferenced_citation_ids": audit.unreferenced_citation_ids,
    }


def contradiction_audit_to_payload(audit: ContradictionAudit) -> dict[str, object]:
    return {
        "checked": audit.checked,
        "conflict_count": audit.conflict_count,
        "findings": [
            {
                "segment_ids": finding.segment_ids,
                "shared_terms": finding.shared_terms,
                "summary": finding.summary,
            }
            for finding in audit.findings
        ],
    }


def multi_hop_audit_to_payload(audit: MultiHopAudit) -> dict[str, object]:
    return {
        "checked": audit.checked,
        "requires_multi_hop": audit.requires_multi_hop,
        "status": audit.status,
        "document_count": audit.document_count,
        "bridge_terms": audit.bridge_terms,
        "warnings": audit.warnings,
    }


def evidence_route_to_payload(route: EvidenceRoute) -> dict[str, object]:
    return {
        "coverage_level": route.coverage_level,
        "segment_count": route.segment_count,
        "document_count": route.document_count,
        "anchor_count": route.anchor_count,
        "multi_document": route.multi_document,
        "has_neighbor_context": route.has_neighbor_context,
        "warnings": route.warnings,
        "documents": [
            {
                "document_id": document.document_id,
                "title": document.title,
                "segment_ids": document.segment_ids,
                "anchors": document.anchors,
            }
            for document in route.documents
        ],
    }
