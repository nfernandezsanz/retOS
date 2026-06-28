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
class QueryPlanStep:
    name: str
    description: str
    status: str


@dataclass(frozen=True)
class QueryPlan:
    strategy: str
    requires_multi_hop: bool
    search_queries: list[str]
    expected_evidence: str
    steps: list[QueryPlanStep]
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


def plan_query(question: str) -> QueryPlan:
    normalized_question = " ".join(question.split())
    question_terms = significant_terms(normalized_question)
    question_tokens = set(re.findall(r"[a-z0-9]+", normalized_question.lower()))
    requires_multi_hop = bool(question_tokens & MULTI_HOP_MARKERS)
    search_queries = query_searches(normalized_question)
    expected_evidence = "multi_document" if requires_multi_hop else "single_document_or_abstain"
    strategy = "multi_hop_evidence_route" if requires_multi_hop else "direct_evidence_lookup"
    warnings: list[str] = []
    if len(question_terms) < 2:
        warnings.append("low_specificity_question")
    if requires_multi_hop and len(search_queries) < 2:
        warnings.append("multi_hop_question_without_distinct_subqueries")

    steps = [
        QueryPlanStep(
            name="search",
            description="Run bounded BM25 search over the selected domain.",
            status="planned",
        ),
        QueryPlanStep(
            name="read",
            description="Read only citations returned by controlled corpus search.",
            status="planned",
        ),
        QueryPlanStep(
            name="route",
            description=f"Expect {expected_evidence.replace('_', ' ')} evidence coverage.",
            status="planned",
        ),
        QueryPlanStep(
            name="audit",
            description="Persist evidence, contradiction, multi-hop, and budget audits.",
            status="planned",
        ),
    ]

    return QueryPlan(
        strategy=strategy,
        requires_multi_hop=requires_multi_hop,
        search_queries=search_queries,
        expected_evidence=expected_evidence,
        steps=steps,
        warnings=warnings,
    )


def query_searches(question: str) -> list[str]:
    candidates = [
        candidate.strip(" ,.;:?!")
        for candidate in re.split(
            r"\b(?:and|versus|vs|compare|between|while|during|after|before)\b",
            question,
            flags=re.IGNORECASE,
        )
        if candidate.strip(" ,.;:?!")
    ]
    searches: list[str] = []
    for candidate in candidates or [question]:
        terms = sorted(significant_terms(candidate))
        rendered = " ".join(terms) if terms else candidate
        if rendered and rendered not in searches:
            searches.append(rendered[:160])
    if question not in searches:
        searches.insert(0, question[:160])
    return searches[:4]


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


def query_plan_to_payload(plan: QueryPlan) -> dict[str, object]:
    return {
        "strategy": plan.strategy,
        "requires_multi_hop": plan.requires_multi_hop,
        "search_queries": plan.search_queries,
        "expected_evidence": plan.expected_evidence,
        "warnings": plan.warnings,
        "steps": [
            {
                "name": step.name,
                "description": step.description,
                "status": step.status,
            }
            for step in plan.steps
        ],
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
