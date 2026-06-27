from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from retos.agent.service import build_grounded_answer, citation_from_hit
from retos.search.index import IndexedSegment, SearchHit, TantivySearchIndex


@dataclass(frozen=True)
class EvalDocument:
    id: str
    title: str
    text: str
    anchor: str


@dataclass(frozen=True)
class EvalCase:
    id: str
    question: str
    documents: tuple[EvalDocument, ...]
    expected_citation_titles: tuple[str, ...]
    expected_answer_terms: tuple[str, ...]
    expect_abstention: bool = False
    max_citations: int = 5


@dataclass(frozen=True)
class EvalCaseResult:
    case_id: str
    question: str
    passed: bool
    retrieval_recall: bool
    citation_validity: bool
    grounded_answer: bool
    abstention: bool
    budget_compliance: bool
    answer: str
    citations: tuple[dict[str, Any], ...]
    failures: tuple[str, ...]


@dataclass(frozen=True)
class EvalSuiteReport:
    suite_name: str
    passed: bool
    case_count: int
    retrieval_recall: float
    citation_validity: float
    grounded_answer: float
    abstention: float
    budget_compliance: float
    cases: tuple[EvalCaseResult, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite_name": self.suite_name,
            "passed": self.passed,
            "case_count": self.case_count,
            "metrics": {
                "retrieval_recall": self.retrieval_recall,
                "citation_validity": self.citation_validity,
                "grounded_answer": self.grounded_answer,
                "abstention": self.abstention,
                "budget_compliance": self.budget_compliance,
            },
            "cases": [
                {
                    "case_id": case.case_id,
                    "question": case.question,
                    "passed": case.passed,
                    "retrieval_recall": case.retrieval_recall,
                    "citation_validity": case.citation_validity,
                    "grounded_answer": case.grounded_answer,
                    "abstention": case.abstention,
                    "budget_compliance": case.budget_compliance,
                    "answer": case.answer,
                    "citations": list(case.citations),
                    "failures": list(case.failures),
                }
                for case in self.cases
            ],
        }

    def to_markdown(self) -> str:
        lines = [
            f"# Eval Report: {self.suite_name}",
            "",
            f"Status: {'PASS' if self.passed else 'FAIL'}",
            "",
            "| Metric | Score |",
            "| --- | ---: |",
            f"| Retrieval recall | {self.retrieval_recall:.2f} |",
            f"| Citation validity | {self.citation_validity:.2f} |",
            f"| Grounded answer | {self.grounded_answer:.2f} |",
            f"| Abstention | {self.abstention:.2f} |",
            f"| Budget compliance | {self.budget_compliance:.2f} |",
            "",
            "| Case | Status | Failures |",
            "| --- | --- | --- |",
        ]
        for case in self.cases:
            failures = ", ".join(case.failures) if case.failures else "-"
            lines.append(f"| {case.case_id} | {'PASS' if case.passed else 'FAIL'} | {failures} |")
        return "\n".join(lines) + "\n"


def smoke_eval_cases() -> tuple[EvalCase, ...]:
    return (
        EvalCase(
            id="apollo-guidance",
            question="What did Apollo guidance computers use for mission operations?",
            documents=(
                EvalDocument(
                    id="apollo",
                    title="Apollo Guidance Notes",
                    text=(
                        "Apollo guidance computers used deterministic checklists and "
                        "redundant mission procedures during lunar operations."
                    ),
                    anchor="fixture://apollo#p1",
                ),
                EvalDocument(
                    id="biology",
                    title="Marine Biology Notes",
                    text="Ocean biology notes mention plankton, salinity, and coastal sampling.",
                    anchor="fixture://biology#p1",
                ),
            ),
            expected_citation_titles=("Apollo Guidance Notes",),
            expected_answer_terms=("deterministic checklists",),
        ),
        EvalCase(
            id="marine-salinity",
            question="Which notes mention salinity and plankton?",
            documents=(
                EvalDocument(
                    id="biology",
                    title="Marine Biology Notes",
                    text="Ocean biology notes mention plankton, salinity, and coastal sampling.",
                    anchor="fixture://biology#p1",
                ),
                EvalDocument(
                    id="apollo",
                    title="Apollo Guidance Notes",
                    text="Apollo guidance computers used deterministic checklists.",
                    anchor="fixture://apollo#p1",
                ),
            ),
            expected_citation_titles=("Marine Biology Notes",),
            expected_answer_terms=("plankton", "salinity"),
        ),
        EvalCase(
            id="no-evidence",
            question="Which document explains medieval ceramic kiln temperatures?",
            documents=(
                EvalDocument(
                    id="apollo",
                    title="Apollo Guidance Notes",
                    text="Apollo guidance computers used deterministic checklists.",
                    anchor="fixture://apollo#p1",
                ),
            ),
            expected_citation_titles=(),
            expected_answer_terms=(),
            expect_abstention=True,
        ),
    )


def segments_for_case(case: EvalCase) -> list[IndexedSegment]:
    return [
        IndexedSegment(
            segment_id=f"{case.id}-{document.id}-segment-0",
            document_id=f"{case.id}-{document.id}",
            document_version_id=f"{case.id}-{document.id}-v1",
            title=document.title,
            text=document.text,
            anchor=document.anchor,
            ordinal=index,
        )
        for index, document in enumerate(case.documents)
    ]


def citation_payloads(hits: Iterable[SearchHit]) -> tuple[dict[str, Any], ...]:
    citations = [citation_from_hit(hit) for hit in hits]
    return tuple(
        {
            "segment_id": citation.segment_id,
            "document_id": citation.document_id,
            "document_version_id": citation.document_version_id,
            "title": citation.title,
            "anchor": citation.anchor,
            "score": citation.score,
            "text": citation.text,
        }
        for citation in citations
    )


def score_case(case: EvalCase, hits: list[SearchHit], answer: str) -> EvalCaseResult:
    hit_titles = {hit.title for hit in hits}
    expected_titles = set(case.expected_citation_titles)
    known_segment_ids = {segment.segment_id for segment in segments_for_case(case)}
    answer_lower = answer.lower()

    retrieval_recall = expected_titles.issubset(hit_titles)
    citation_validity = all(hit.segment_id in known_segment_ids and hit.anchor for hit in hits)
    grounded_answer = all(term.lower() in answer_lower for term in case.expected_answer_terms)
    abstention = (
        (not hits and "could not find enough indexed evidence" in answer_lower)
        if (case.expect_abstention)
        else True
    )
    budget_compliance = len(hits) <= case.max_citations

    failures: list[str] = []
    if not retrieval_recall:
        failures.append("retrieval_recall")
    if not citation_validity:
        failures.append("citation_validity")
    if not grounded_answer:
        failures.append("grounded_answer")
    if not abstention:
        failures.append("abstention")
    if not budget_compliance:
        failures.append("budget_compliance")

    return EvalCaseResult(
        case_id=case.id,
        question=case.question,
        passed=not failures,
        retrieval_recall=retrieval_recall,
        citation_validity=citation_validity,
        grounded_answer=grounded_answer,
        abstention=abstention,
        budget_compliance=budget_compliance,
        answer=answer,
        citations=citation_payloads(hits),
        failures=tuple(failures),
    )


def ratio(values: Iterable[bool]) -> float:
    items = tuple(values)
    if not items:
        return 1.0
    return sum(1 for item in items if item) / len(items)


def run_smoke_eval_suite(
    *,
    index_root: str | Path,
    suite_name: str = "retos-smoke",
    cases: tuple[EvalCase, ...] | None = None,
) -> EvalSuiteReport:
    index = TantivySearchIndex(index_root)
    eval_cases = cases or smoke_eval_cases()
    results: list[EvalCaseResult] = []

    for case in eval_cases:
        domain_id = f"eval-{case.id}"
        index.rebuild_domain(domain_id, segments_for_case(case))
        hits = index.search_domain(domain_id, case.question, limit=case.max_citations)
        answer = build_grounded_answer(case.question, hits)
        results.append(score_case(case, hits, answer))

    return EvalSuiteReport(
        suite_name=suite_name,
        passed=all(case.passed for case in results),
        case_count=len(results),
        retrieval_recall=ratio(case.retrieval_recall for case in results),
        citation_validity=ratio(case.citation_validity for case in results),
        grounded_answer=ratio(case.grounded_answer for case in results),
        abstention=ratio(case.abstention for case in results),
        budget_compliance=ratio(case.budget_compliance for case in results),
        cases=tuple(results),
    )
