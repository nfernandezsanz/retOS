from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from retos.api.routes.events import progress_store
from retos.core.config import Settings
from retos.llm.providers import active_provider
from retos.persistence.unit_of_work import SQLAlchemyUnitOfWork
from retos.search.index import SearchHit, SearchIndexMissingError, TantivySearchIndex


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
        limit = int(job.payload.get("limit") or 5)
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
            },
        )

        try:
            hits = index.search_domain(domain.id, question, limit=limit)
        except SearchIndexMissingError as exc:
            raise AgentQueryError("Search index has not been built for this domain") from exc

        result = AgentQueryResult(
            job_id=job.id,
            domain_id=domain.id,
            question=question,
            answer=build_grounded_answer(question, hits),
            citations=[citation_from_hit(hit) for hit in hits],
            provider=provider.provider,
            model=provider.model,
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
            },
        )
        await uow.commit()

    progress_store.append(
        "agent.completed",
        {
            "job_id": job_id,
            "domain_id": result.domain_id,
            "citation_count": len(result.citations),
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
