from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from retos.agent.harness import create_research_harness
from retos.agent.tools import (
    CorpusToolbox,
    CorpusToolError,
    create_corpus_toolbox,
    select_hits_within_evidence_budget,
    token_count,
)
from retos.api.routes.events import progress_store
from retos.core.config import Settings
from retos.llm.providers import active_provider
from retos.persistence.unit_of_work import SQLAlchemyUnitOfWork
from retos.search.index import SearchHit, SearchIndexMissingError, TantivySearchIndex

DEFAULT_AGENT_BUDGET: dict[str, int] = {
    "max_searches": 8,
    "max_citations": 5,
    "max_evidence_tokens": 16_000,
    "max_runtime_seconds": 120,
}


@dataclass(frozen=True)
class AgentBudget:
    max_searches: int
    max_citations: int
    max_evidence_tokens: int
    max_runtime_seconds: int


@dataclass(frozen=True)
class AgentBudgetUsage:
    search_count: int
    citation_count: int
    evidence_tokens: int
    runtime_ms: int
    budget: AgentBudget
    within_budget: bool


@dataclass(frozen=True)
class EvidenceAudit:
    grounded: bool
    cited_segment_ids: list[str]
    unreferenced_citation_ids: list[str]


@dataclass(frozen=True)
class Citation:
    segment_id: str
    document_id: str
    document_version_id: str
    title: str
    anchor: str | None
    score: float
    text: str


@dataclass(frozen=True)
class AgentQueryResult:
    job_id: str
    domain_id: str
    question: str
    answer: str
    citations: list[Citation]
    provider: str
    model: str
    runtime: str
    evidence_audit: EvidenceAudit
    usage: AgentBudgetUsage


class AgentQueryError(RuntimeError):
    pass


def citation_from_hit(hit: SearchHit) -> Citation:
    return Citation(
        segment_id=hit.segment_id,
        document_id=hit.document_id,
        document_version_id=hit.document_version_id,
        title=hit.title,
        anchor=hit.anchor,
        score=hit.score,
        text=hit.text,
    )


def build_grounded_answer(question: str, hits: list[SearchHit]) -> str:
    if not hits:
        return (
            "I could not find enough indexed evidence to answer this question. "
            "Rebuild the index or ingest more documents, then try again."
        )
    evidence = " ".join(hit.text.strip() for hit in hits[:3] if hit.text.strip())
    citation_ids = ", ".join(hit.segment_id for hit in hits)
    return (
        f"Grounded answer for: {question}\n\n"
        f"The indexed evidence points to: {evidence}\n\n"
        f"Evidence ledger: {citation_ids}\n\n"
        "Review the citations before using this answer."
    )


def build_deepagents_prompt(
    *,
    question: str,
    seed_payload: dict[str, object],
    budget: AgentBudget,
) -> str:
    return (
        "Answer this RetOS research question using only RetOS corpus evidence.\n\n"
        f"Question: {question}\n\n"
        "Seed evidence returned by search_corpus:\n"
        f"{seed_payload}\n\n"
        "Rules:\n"
        "- Use segment_id values from the evidence when making factual claims.\n"
        "- You may call search_corpus for additional evidence within budget.\n"
        "- You may call read_citation only for segment ids returned by search_corpus.\n"
        "- Abstain if the returned evidence is insufficient.\n\n"
        "Budget:\n"
        f"- max_searches={budget.max_searches}\n"
        f"- max_citations={budget.max_citations}\n"
        f"- max_evidence_tokens={budget.max_evidence_tokens}\n"
        f"- max_runtime_seconds={budget.max_runtime_seconds}"
    )


def text_from_message_content(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, Mapping):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return ""


def extract_harness_answer(output: object) -> str:
    if isinstance(output, str):
        return output.strip()
    if isinstance(output, Mapping):
        answer = output.get("answer") or output.get("structured_response")
        if isinstance(answer, str):
            return answer.strip()
        messages = output.get("messages")
        if isinstance(messages, list):
            for message in reversed(messages):
                if isinstance(message, Mapping):
                    content = text_from_message_content(message.get("content"))
                else:
                    content = text_from_message_content(getattr(message, "content", ""))
                if content.strip():
                    return content.strip()
    content = text_from_message_content(getattr(output, "content", ""))
    return content.strip()


def invoke_deepagents_harness(*, settings: Settings, toolbox: CorpusToolbox, prompt: str) -> str:
    harness = create_research_harness(
        settings=settings,
        tools=[toolbox.search_corpus, toolbox.read_citation],
    )
    invoke = getattr(harness, "invoke", None)
    if not callable(invoke):
        raise AgentQueryError("Deep Agents harness does not expose invoke()")
    output = invoke(
        {"messages": [{"role": "user", "content": prompt}]},
        config={"recursion_limit": 25},
    )
    answer = extract_harness_answer(output)
    if not answer:
        raise AgentQueryError("Deep Agents harness returned an empty answer")
    return answer


def synthesize_agent_answer(
    *,
    settings: Settings,
    question: str,
    seed_payload: dict[str, object],
    toolbox: CorpusToolbox,
    budget: AgentBudget,
) -> str:
    if settings.agent_runtime == "deterministic":
        return build_grounded_answer(question, toolbox.selected_hits)
    prompt = build_deepagents_prompt(
        question=question,
        seed_payload=seed_payload,
        budget=budget,
    )
    return invoke_deepagents_harness(settings=settings, toolbox=toolbox, prompt=prompt)


def audit_evidence(answer: str, citations: list[Citation]) -> EvidenceAudit:
    citation_ids = [citation.segment_id for citation in citations]
    cited_ids = [segment_id for segment_id in citation_ids if segment_id in answer]
    unreferenced_ids = [segment_id for segment_id in citation_ids if segment_id not in cited_ids]
    return EvidenceAudit(
        grounded=not citations or bool(cited_ids),
        cited_segment_ids=cited_ids,
        unreferenced_citation_ids=unreferenced_ids,
    )


def ensure_evidence_ledger(answer: str, citations: list[Citation]) -> tuple[str, EvidenceAudit]:
    audit = audit_evidence(answer, citations)
    if audit.grounded or not citations:
        return answer, audit
    ledger = ", ".join(citation.segment_id for citation in citations)
    updated_answer = f"{answer.rstrip()}\n\nEvidence ledger: {ledger}"
    return updated_answer, audit_evidence(updated_answer, citations)


def parse_positive_int_budget(
    payload: dict[str, object],
    key: str,
    *,
    default: int,
) -> int:
    value = payload.get(key, default)
    if isinstance(value, bool):
        raise AgentQueryError(f"{key} must be a positive integer")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = int(value)
        except ValueError as exc:
            raise AgentQueryError(f"{key} must be a positive integer") from exc
    else:
        raise AgentQueryError(f"{key} must be a positive integer")
    if parsed < 1:
        raise AgentQueryError(f"{key} must be a positive integer")
    return parsed


def budget_from_payload(payload: dict[str, object]) -> AgentBudget:
    raw_budget = payload.get("budget")
    if raw_budget is None:
        budget_payload: dict[str, object] = {}
    elif isinstance(raw_budget, dict):
        budget_payload = raw_budget
    else:
        raise AgentQueryError("budget must be an object")
    return AgentBudget(
        max_searches=parse_positive_int_budget(
            budget_payload,
            "max_searches",
            default=DEFAULT_AGENT_BUDGET["max_searches"],
        ),
        max_citations=parse_positive_int_budget(
            budget_payload,
            "max_citations",
            default=DEFAULT_AGENT_BUDGET["max_citations"],
        ),
        max_evidence_tokens=parse_positive_int_budget(
            budget_payload,
            "max_evidence_tokens",
            default=DEFAULT_AGENT_BUDGET["max_evidence_tokens"],
        ),
        max_runtime_seconds=parse_positive_int_budget(
            budget_payload,
            "max_runtime_seconds",
            default=DEFAULT_AGENT_BUDGET["max_runtime_seconds"],
        ),
    )


def budget_to_payload(budget: AgentBudget) -> dict[str, int]:
    return {
        "max_searches": budget.max_searches,
        "max_citations": budget.max_citations,
        "max_evidence_tokens": budget.max_evidence_tokens,
        "max_runtime_seconds": budget.max_runtime_seconds,
    }


def hits_within_budget(hits: list[SearchHit], budget: AgentBudget) -> list[SearchHit]:
    return select_hits_within_evidence_budget(
        hits,
        max_citations=budget.max_citations,
        max_evidence_tokens=budget.max_evidence_tokens,
    )


def usage_to_payload(usage: AgentBudgetUsage) -> dict[str, object]:
    return {
        "budget": budget_to_payload(usage.budget),
        "search_count": usage.search_count,
        "citation_count": usage.citation_count,
        "evidence_tokens": usage.evidence_tokens,
        "runtime_ms": usage.runtime_ms,
        "within_budget": usage.within_budget,
    }


def evidence_audit_to_payload(audit: EvidenceAudit) -> dict[str, object]:
    return {
        "grounded": audit.grounded,
        "cited_segment_ids": audit.cited_segment_ids,
        "unreferenced_citation_ids": audit.unreferenced_citation_ids,
    }


def result_payload(
    *,
    original_payload: dict[str, object],
    result: AgentQueryResult,
) -> dict[str, object]:
    return {
        **original_payload,
        "result": {
            "answer": result.answer,
            "provider": result.provider,
            "model": result.model,
            "runtime": result.runtime,
            "evidence_audit": evidence_audit_to_payload(result.evidence_audit),
            "usage": usage_to_payload(result.usage),
            "citations": [
                {
                    "segment_id": citation.segment_id,
                    "document_id": citation.document_id,
                    "document_version_id": citation.document_version_id,
                    "title": citation.title,
                    "anchor": citation.anchor,
                    "score": citation.score,
                    "text": citation.text,
                }
                for citation in result.citations
            ],
        },
    }


async def run_agent_query(
    *,
    job_id: str,
    uow: SQLAlchemyUnitOfWork,
    index: TantivySearchIndex,
    settings: Settings,
    actor: str = "system:worker",
) -> AgentQueryResult:
    started_at = datetime.now(UTC)
    async with uow:
        job = await uow.jobs.get(job_id)
        if job is None:
            raise AgentQueryError("Job not found")
        if job.kind != "agent.query":
            raise AgentQueryError(f"Unsupported agent job kind: {job.kind}")
        if job.status != "queued":
            raise AgentQueryError(f"Job must be queued, got {job.status}")
        if job.domain_id is None:
            raise AgentQueryError("Agent query requires a domain_id")

        domain = await uow.domains.get(job.domain_id)
        if domain is None:
            raise AgentQueryError("Domain not found")

        question = str(job.payload.get("question") or "").strip()
        if not question:
            raise AgentQueryError("Agent query requires a question")
        limit = parse_positive_int_budget(
            job.payload,
            "limit",
            default=DEFAULT_AGENT_BUDGET["max_citations"],
        )
        budget = budget_from_payload(job.payload)
        provider = active_provider(settings)
        if not provider.can_call:
            raise AgentQueryError(provider.reason or "Active provider is not callable")
        if provider.paid and not settings.allow_paid_llm:
            raise AgentQueryError("Paid LLM providers are disabled")

        await uow.jobs.update_status(job_id=job.id, status="running", started_at=started_at)
        await uow.journal_events.add(
            actor=actor,
            event_type="job.running",
            entity_type="job",
            entity_id=job.id,
            payload={"from_status": job.status, "to_status": "running"},
        )
        await uow.progress_events.add(
            job_id=job.id,
            event_type="agent.started",
            message=f"Started research query for {domain.slug}",
            payload={
                "domain_id": domain.id,
                "domain_slug": domain.slug,
                "provider": provider.provider,
                "model": provider.model,
                "runtime": settings.agent_runtime,
                "budget": budget_to_payload(budget),
            },
        )

        toolbox = create_corpus_toolbox(
            index=index,
            domain_id=domain.id,
            max_searches=budget.max_searches,
            max_citations=budget.max_citations,
            max_evidence_tokens=budget.max_evidence_tokens,
        )
        try:
            seed_payload = toolbox.search_corpus(
                question,
                limit=min(limit, budget.max_citations),
            )
        except CorpusToolError as exc:
            if not isinstance(exc.__cause__, SearchIndexMissingError):
                raise AgentQueryError(str(exc)) from exc
            raise AgentQueryError("Search index has not been built for this domain") from exc
        hits = toolbox.selected_hits
        answer = synthesize_agent_answer(
            settings=settings,
            question=question,
            seed_payload=seed_payload,
            toolbox=toolbox,
            budget=budget,
        )
        if not toolbox.selected_hits:
            answer = build_grounded_answer(question, [])
        hits = toolbox.selected_hits
        citations = [citation_from_hit(hit) for hit in hits]
        answer, evidence_audit = ensure_evidence_ledger(answer, citations)
        runtime_ms = int((datetime.now(UTC) - started_at).total_seconds() * 1000)
        usage = AgentBudgetUsage(
            search_count=toolbox.search_count,
            citation_count=len(hits),
            evidence_tokens=sum(token_count(hit.text) for hit in hits),
            runtime_ms=runtime_ms,
            budget=budget,
            within_budget=(
                toolbox.search_count <= budget.max_searches
                and len(hits) <= budget.max_citations
                and sum(token_count(hit.text) for hit in hits) <= budget.max_evidence_tokens
                and runtime_ms <= budget.max_runtime_seconds * 1000
            ),
        )

        result = AgentQueryResult(
            job_id=job.id,
            domain_id=domain.id,
            question=question,
            answer=answer,
            citations=citations,
            provider=provider.provider,
            model=provider.model,
            runtime=settings.agent_runtime,
            evidence_audit=evidence_audit,
            usage=usage,
        )
        completed_at = datetime.now(UTC)
        await uow.jobs.update_payload(
            job_id=job.id,
            payload=result_payload(original_payload=job.payload, result=result),
        )
        await uow.jobs.update_status(
            job_id=job.id,
            status="succeeded",
            completed_at=completed_at,
        )
        await uow.journal_events.add(
            actor=actor,
            event_type="agent.completed",
            entity_type="job",
            entity_id=job.id,
            payload={
                "domain_id": domain.id,
                "citation_count": len(result.citations),
                "provider": result.provider,
                "model": result.model,
                "runtime": result.runtime,
                "evidence_audit": evidence_audit_to_payload(result.evidence_audit),
                "usage": usage_to_payload(result.usage),
            },
        )
        await uow.journal_events.add(
            actor=actor,
            event_type="job.succeeded",
            entity_type="job",
            entity_id=job.id,
            payload={"from_status": "running", "to_status": "succeeded"},
        )
        await uow.progress_events.add(
            job_id=job.id,
            event_type="agent.completed",
            message=f"Completed research query with {len(result.citations)} citations",
            payload={
                "domain_id": domain.id,
                "citation_count": len(result.citations),
                "provider": result.provider,
                "model": result.model,
                "runtime": result.runtime,
                "evidence_audit": evidence_audit_to_payload(result.evidence_audit),
                "usage": usage_to_payload(result.usage),
            },
        )
        await uow.commit()

    progress_store.append(
        "agent.completed",
        {
            "job_id": job_id,
            "domain_id": result.domain_id,
            "citation_count": len(result.citations),
            "runtime": result.runtime,
            "grounded": result.evidence_audit.grounded,
            "within_budget": result.usage.within_budget,
            "search_count": result.usage.search_count,
            "evidence_tokens": result.usage.evidence_tokens,
        },
    )
    return result


async def fail_agent_query_job(
    *,
    job_id: str,
    uow: SQLAlchemyUnitOfWork,
    error: str,
    actor: str = "system:worker",
) -> None:
    completed_at = datetime.now(UTC)
    async with uow:
        job = await uow.jobs.get(job_id)
        if job is None:
            return
        await uow.jobs.update_status(
            job_id=job.id,
            status="failed",
            completed_at=completed_at,
            error=error,
        )
        await uow.journal_events.add(
            actor=actor,
            event_type="job.failed",
            entity_type="job",
            entity_id=job.id,
            payload={"error": error},
        )
        await uow.progress_events.add(
            job_id=job.id,
            event_type="agent.failed",
            message="Research query failed",
            payload={"error": error},
        )
        await uow.commit()

    progress_store.append("agent.failed", {"job_id": job_id, "error": error})
