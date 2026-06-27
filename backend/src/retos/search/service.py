from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from retos.api.routes.events import progress_store
from retos.persistence.unit_of_work import SQLAlchemyUnitOfWork
from retos.search.index import TantivySearchIndex


@dataclass(frozen=True)
class RebuildIndexResult:
    domain_id: str
    segment_count: int


class SearchIndexingError(RuntimeError):
    pass


async def rebuild_domain_index(
    *,
    job_id: str,
    uow: SQLAlchemyUnitOfWork,
    index: TantivySearchIndex,
    actor: str = "system:worker",
) -> RebuildIndexResult:
    started_at = datetime.now(UTC)
    async with uow:
        job = await uow.jobs.get(job_id)
        if job is None:
            raise SearchIndexingError("Job not found")
        if job.kind != "index.domain":
            raise SearchIndexingError(f"Unsupported index job kind: {job.kind}")
        if job.status != "queued":
            raise SearchIndexingError(f"Job must be queued, got {job.status}")
        if job.domain_id is None:
            raise SearchIndexingError("Index job requires a domain_id")

        domain = await uow.domains.get(job.domain_id)
        if domain is None:
            raise SearchIndexingError("Domain not found")

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
            event_type="index.started",
            message=f"Started BM25 index rebuild for {domain.slug}",
            payload={"domain_id": domain.id, "domain_slug": domain.slug},
        )

        segments = await uow.documents.list_indexable_segments(domain.id)
        segment_count = index.rebuild_domain(domain.id, segments)

        completed_at = datetime.now(UTC)
        await uow.jobs.update_status(
            job_id=job.id,
            status="succeeded",
            completed_at=completed_at,
        )
        await uow.journal_events.add(
            actor=actor,
            event_type="index.rebuilt",
            entity_type="domain",
            entity_id=domain.id,
            payload={"job_id": job.id, "segment_count": segment_count},
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
            event_type="index.completed",
            message=f"Indexed {segment_count} segments",
            payload={"domain_id": domain.id, "segment_count": segment_count},
        )
        await uow.commit()

    progress_store.append(
        "index.completed",
        {"job_id": job_id, "domain_id": domain.id, "segment_count": segment_count},
    )
    return RebuildIndexResult(domain_id=domain.id, segment_count=segment_count)


async def fail_index_job(
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
            event_type="index.failed",
            message="BM25 index rebuild failed",
            payload={"error": error},
        )
        await uow.commit()

    progress_store.append("index.failed", {"job_id": job_id, "error": error})
