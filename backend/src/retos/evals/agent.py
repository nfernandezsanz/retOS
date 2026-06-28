from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from retos.agent.audits import (
    audit_evidence_route,
    audit_multi_hop,
    evidence_audit_to_payload,
    evidence_route_to_payload,
    multi_hop_audit_to_payload,
    plan_query,
    query_plan_to_payload,
)
from retos.agent.service import (
    AgentBudget,
    budget_to_payload,
    build_grounded_answer,
    citation_from_hit,
    seed_agent_evidence,
)
from retos.agent.tools import create_corpus_toolbox, token_count
from retos.evals.smoke import EvalDocument, markdown_cell
from retos.search.index import IndexedSegment, TantivySearchIndex


@dataclass(frozen=True)
class AgentEvalCase:
    id: str
    question: str
    documents: tuple[EvalDocument, ...]
    expected_citation_titles: tuple[str, ...]
    expected_answer_terms: tuple[str, ...]
    expected_bridge_terms: tuple[str, ...]
    min_search_count: int = 2
    max_citations: int = 5
    max_searches: int = 4
    max_evidence_tokens: int = 120


@dataclass(frozen=True)
class AgentEvalCaseResult:
    case_id: str
    question: str
    passed: bool
    query_plan: bool
    multi_hop_support: bool
    evidence_route: bool
    citation_validity: bool
    grounded_answer: bool
    budget_compliance: bool
    answer: str
    citations: tuple[dict[str, Any], ...]
    usage: dict[str, Any]
    audits: dict[str, Any]
    failures: tuple[str, ...]


@dataclass(frozen=True)
class AgentEvalSuiteReport:
    suite_name: str
    passed: bool
    case_count: int
    query_plan: float
    multi_hop_support: float
    evidence_route: float
    citation_validity: float
    grounded_answer: float
    budget_compliance: float
    cases: tuple[AgentEvalCaseResult, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite_name": self.suite_name,
            "passed": self.passed,
            "case_count": self.case_count,
            "metadata": self.metadata,
            "metrics": {
                "query_plan": self.query_plan,
                "multi_hop_support": self.multi_hop_support,
                "evidence_route": self.evidence_route,
                "citation_validity": self.citation_validity,
                "grounded_answer": self.grounded_answer,
                "budget_compliance": self.budget_compliance,
            },
            "cases": [
                {
                    "case_id": case.case_id,
                    "question": case.question,
                    "passed": case.passed,
                    "query_plan": case.query_plan,
                    "multi_hop_support": case.multi_hop_support,
                    "evidence_route": case.evidence_route,
                    "citation_validity": case.citation_validity,
                    "grounded_answer": case.grounded_answer,
                    "budget_compliance": case.budget_compliance,
                    "answer": case.answer,
                    "citations": list(case.citations),
                    "usage": case.usage,
                    "audits": case.audits,
                    "failures": list(case.failures),
                }
                for case in self.cases
            ],
        }

    def to_markdown(self) -> str:
        lines = [
            f"# Agent Eval Report: {self.suite_name}",
            "",
            f"Status: {'PASS' if self.passed else 'FAIL'}",
            "",
            "| Metric | Score |",
            "| --- | ---: |",
            f"| Query plan | {self.query_plan:.2f} |",
            f"| Multi-hop support | {self.multi_hop_support:.2f} |",
            f"| Evidence route | {self.evidence_route:.2f} |",
            f"| Citation validity | {self.citation_validity:.2f} |",
            f"| Grounded answer | {self.grounded_answer:.2f} |",
            f"| Budget compliance | {self.budget_compliance:.2f} |",
        ]
        if self.metadata:
            lines.extend(
                [
                    "",
                    "| Metadata | Value |",
                    "| --- | --- |",
                    *(
                        f"| {markdown_cell(key)} | {markdown_cell(value)} |"
                        for key, value in sorted(self.metadata.items())
                    ),
                ]
            )
        lines.extend(
            [
                "",
                "| Case | Status | Failures |",
                "| --- | --- | --- |",
            ]
        )
        for case in self.cases:
            failures = ", ".join(case.failures) if case.failures else "-"
            lines.append(f"| {case.case_id} | {'PASS' if case.passed else 'FAIL'} | {failures} |")
        return "\n".join(lines) + "\n"


def agent_multihop_eval_cases() -> tuple[AgentEvalCase, ...]:
    return (
        AgentEvalCase(
            id="apollo-telemetry-bridge",
            question="Compare Apollo checklist review and telemetry guidance",
            documents=(
                EvalDocument(
                    id="apollo-review",
                    title="Apollo Review Notes",
                    text="Apollo checklist review confirmed guidance readiness.",
                    anchor="fixture://agent/apollo-review#p1",
                ),
                EvalDocument(
                    id="telemetry-review",
                    title="Telemetry Review Notes",
                    text="Mission checklist review compared guidance telemetry.",
                    anchor="fixture://agent/telemetry-review#p1",
                ),
            ),
            expected_citation_titles=("Apollo Review Notes", "Telemetry Review Notes"),
            expected_answer_terms=("checklist review", "guidance"),
            expected_bridge_terms=("checklist", "guidance", "review"),
        ),
        AgentEvalCase(
            id="invoice-retention-policy",
            question="Compare invoice approval and retention policy evidence",
            documents=(
                EvalDocument(
                    id="invoice-approval",
                    title="Invoice Approval Policy",
                    text=(
                        "Invoice approval policy requires retention review before "
                        "payment release."
                    ),
                    anchor="fixture://agent/invoice-approval#p1",
                ),
                EvalDocument(
                    id="retention-audit",
                    title="Retention Audit Policy",
                    text=(
                        "Retention review policy links invoice approval evidence to "
                        "audit storage."
                    ),
                    anchor="fixture://agent/retention-audit#p1",
                ),
            ),
            expected_citation_titles=("Invoice Approval Policy", "Retention Audit Policy"),
            expected_answer_terms=("invoice approval", "retention review"),
            expected_bridge_terms=("approval", "invoice", "policy", "retention", "review"),
        ),
        AgentEvalCase(
            id="incident-escalation-triage",
            question=(
                "Which same incident response evidence connects triage notes and "
                "escalation policy?"
            ),
            documents=(
                EvalDocument(
                    id="incident-triage",
                    title="Incident Triage Notes",
                    text=(
                        "Incident response triage notes record escalation policy "
                        "evidence and containment review."
                    ),
                    anchor="fixture://agent/incident-triage#p1",
                ),
                EvalDocument(
                    id="escalation-policy",
                    title="Escalation Policy",
                    text=(
                        "Incident response escalation policy requires triage evidence "
                        "before containment review."
                    ),
                    anchor="fixture://agent/escalation-policy#p1",
                ),
            ),
            expected_citation_titles=("Escalation Policy", "Incident Triage Notes"),
            expected_answer_terms=("incident response", "triage evidence"),
            expected_bridge_terms=("evidence", "incident", "policy", "response", "triage"),
            max_citations=2,
            max_evidence_tokens=80,
        ),
    )


def run_agent_multihop_eval_suite(
    *,
    index_root: str | Path,
    suite_name: str = "agent-multihop",
    cases: tuple[AgentEvalCase, ...] | None = None,
    metadata: dict[str, Any] | None = None,
) -> AgentEvalSuiteReport:
    index = TantivySearchIndex(index_root)
    eval_cases = cases or agent_multihop_eval_cases()
    results: list[AgentEvalCaseResult] = []

    for case in eval_cases:
        domain_id = f"agent-eval-{case.id}"
        index.rebuild_domain(domain_id, segments_for_agent_case(case))
        budget = AgentBudget(
            max_searches=case.max_searches,
            max_citations=case.max_citations,
            max_evidence_tokens=case.max_evidence_tokens,
            max_runtime_seconds=120,
        )
        query_plan = plan_query(case.question)
        toolbox = create_corpus_toolbox(
            index=index,
            domain_id=domain_id,
            max_searches=budget.max_searches,
            max_citations=budget.max_citations,
            max_evidence_tokens=budget.max_evidence_tokens,
        )
        seed_agent_evidence(
            question=case.question,
            limit=case.max_citations,
            budget=budget,
            query_plan=query_plan,
            toolbox=toolbox,
        )
        hits = toolbox.selected_hits
        citations = [citation_from_hit(hit) for hit in hits]
        answer, evidence_audit = build_answer_and_evidence_audit(case.question, hits)
        multi_hop_audit = audit_multi_hop(case.question, citations)
        route = audit_evidence_route(citations)
        results.append(
            score_agent_case(
                case=case,
                answer=answer,
                citations=tuple(
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
                ),
                known_segment_ids={segment.segment_id for segment in segments_for_agent_case(case)},
                query_plan=query_plan_to_payload(query_plan),
                multi_hop_audit=multi_hop_audit_to_payload(multi_hop_audit),
                evidence_route=evidence_route_to_payload(route),
                evidence_audit=evidence_audit_to_payload(evidence_audit),
                usage={
                    **toolbox.usage_payload(),
                    "budget": budget_to_payload(budget),
                    "within_budget": (
                        toolbox.search_count <= budget.max_searches
                        and len(hits) <= budget.max_citations
                        and sum(token_count(hit.text) for hit in hits) <= budget.max_evidence_tokens
                    ),
                },
            )
        )

    return AgentEvalSuiteReport(
        suite_name=suite_name,
        passed=all(case.passed for case in results),
        case_count=len(results),
        query_plan=ratio(case.query_plan for case in results),
        multi_hop_support=ratio(case.multi_hop_support for case in results),
        evidence_route=ratio(case.evidence_route for case in results),
        citation_validity=ratio(case.citation_validity for case in results),
        grounded_answer=ratio(case.grounded_answer for case in results),
        budget_compliance=ratio(case.budget_compliance for case in results),
        cases=tuple(results),
        metadata=metadata or {},
    )


def build_answer_and_evidence_audit(question: str, hits: list[Any]) -> tuple[str, Any]:
    from retos.agent.audits import ensure_evidence_ledger

    citations = [citation_from_hit(hit) for hit in hits]
    return ensure_evidence_ledger(build_grounded_answer(question, hits), citations)


def score_agent_case(
    *,
    case: AgentEvalCase,
    answer: str,
    citations: tuple[dict[str, Any], ...],
    known_segment_ids: set[str],
    query_plan: dict[str, Any],
    multi_hop_audit: dict[str, Any],
    evidence_route: dict[str, Any],
    evidence_audit: dict[str, Any],
    usage: dict[str, Any],
) -> AgentEvalCaseResult:
    citation_titles = {str(citation["title"]) for citation in citations}
    citation_validity = all(
        citation["segment_id"] in known_segment_ids and citation["anchor"] for citation in citations
    )
    answer_lower = answer.lower()
    grounded_answer = bool(evidence_audit["grounded"]) and all(
        term.lower() in answer_lower for term in case.expected_answer_terms
    )
    query_plan_ok = (
        query_plan["strategy"] == "multi_hop_evidence_route"
        and query_plan["requires_multi_hop"] is True
        and len(query_plan["search_queries"]) >= case.min_search_count
    )
    multi_hop_support = (
        multi_hop_audit["status"] == "supported_multi_document"
        and set(multi_hop_audit["bridge_terms"]).issuperset(case.expected_bridge_terms)
        and case.expected_citation_titles == tuple(sorted(citation_titles))
    )
    evidence_route_ok = (
        evidence_route["coverage_level"] == "multi_document"
        and evidence_route["document_count"] >= 2
    )
    budget_compliance = (
        usage["within_budget"] is True
        and int(usage["search_count"]) >= case.min_search_count
        and int(usage["search_count"]) <= case.max_searches
        and int(usage["citation_count"]) <= case.max_citations
    )

    failures: list[str] = []
    for name, passed in {
        "query_plan": query_plan_ok,
        "multi_hop_support": multi_hop_support,
        "evidence_route": evidence_route_ok,
        "citation_validity": citation_validity,
        "grounded_answer": grounded_answer,
        "budget_compliance": budget_compliance,
    }.items():
        if not passed:
            failures.append(name)

    return AgentEvalCaseResult(
        case_id=case.id,
        question=case.question,
        passed=not failures,
        query_plan=query_plan_ok,
        multi_hop_support=multi_hop_support,
        evidence_route=evidence_route_ok,
        citation_validity=citation_validity,
        grounded_answer=grounded_answer,
        budget_compliance=budget_compliance,
        answer=answer,
        citations=citations,
        usage=usage,
        audits={
            "evidence": evidence_audit,
            "multi_hop": multi_hop_audit,
            "evidence_route": evidence_route,
            "query_plan": query_plan,
        },
        failures=tuple(failures),
    )


def segments_for_agent_case(case: AgentEvalCase) -> list[IndexedSegment]:
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


def ratio(values: Iterable[bool]) -> float:
    items = tuple(values)
    if not items:
        return 1.0
    return sum(1 for item in items if item) / len(items)
