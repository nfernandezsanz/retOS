from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

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
    return (
        f"Grounded answer for: {question}\n\n"
        f"The indexed evidence points to: {evidence}\n\n"
        "Review the citations before using this answer."
    )


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


def token_count(value: str) -> int:
    return len(value.split())


def hits_within_budget(hits: list[SearchHit], budget: AgentBudget) -> list[SearchHit]:
    selected: list[SearchHit] = []
    evidence_tokens = 0
    for hit in hits[: budget.max_citations]:
        next_tokens = token_count(hit.text)
        if selected and evidence_tokens + next_tokens > budget.max_evidence_tokens:
            break
        if not selected and next_tokens > budget.max_evidence_tokens:
            break
        selected.append(hit)
        evidence_tokens += next_tokens
    return selected


def usage_to_payload(usage: AgentBudgetUsage) -> dict[str, object]:
    return {
        "budget": budget_to_payload(usage.budget),
        "search_count": usage.search_count,
        "citation_count": usage.citation_count,
        "evidence_tokens": usage.evidence_tokens,
        "runtime_ms": usage.runtime_ms,
        "within_budget": usage.within_budget,
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
                "budget": budget_to_payload(budget),
            },
        )

        try:
            raw_hits = index.search_domain(
                domain.id,
                question,
                limit=min(limit, budget.max_citations),
            )
        except SearchIndexMissingError as exc:
            raise AgentQueryError("Search index has not been built for this domain") from exc
        hits = hits_within_budget(raw_hits, budget)
        runtime_ms = int((datetime.now(UTC) - started_at).total_seconds() * 1000)
        usage = AgentBudgetUsage(
            search_count=1,
            citation_count=len(hits),
            evidence_tokens=sum(token_count(hit.text) for hit in hits),
            runtime_ms=runtime_ms,
            budget=budget,
            within_budget=(
                budget.max_searches >= 1
                and len(hits) <= budget.max_citations
                and sum(token_count(hit.text) for hit in hits) <= budget.max_evidence_tokens
                and runtime_ms <= budget.max_runtime_seconds * 1000
            ),
        )

        result = AgentQueryResult(
            job_id=job.id,
            domain_id=domain.id,
            question=question,
            answer=build_grounded_answer(question, hits),
            citations=[citation_from_hit(hit) for hit in hits],
            provider=provider.provider,
            model=provider.model,
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
