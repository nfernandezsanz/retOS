from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


class AuditedCitation(Protocol):
    @property
    def segment_id(self) -> str: ...

    @property
    def text(self) -> str: ...


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


NEGATION_TERMS = frozenset({"no", "not", "never", "without", "absent", "false", "failed"})
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
