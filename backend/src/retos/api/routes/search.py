from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, status
from pydantic import BaseModel, Field

from retos.api.dependencies import AdminSubjectDep, SettingsDep, UnitOfWorkDep, ViewerSubjectDep
from retos.api.routes.events import progress_store
from retos.api.routes.jobs import JobRead
from retos.domain.jobs import Job
from retos.jobs.tasks import rebuild_domain_index_job
from retos.search.index import SearchHit, SearchIndexMissingError, TantivySearchIndex
from retos.search.service import rebuild_domain_index

router = APIRouter(tags=["search"])


class SearchHitRead(BaseModel):
    segment_id: str
    document_id: str
    document_version_id: str
    title: str
    text: str
    anchor: str | None
    ordinal: int
    score: float

    @classmethod
    def from_hit(cls, hit: SearchHit) -> SearchHitRead:
        return cls(
            segment_id=hit.segment_id,
            document_id=hit.document_id,
            document_version_id=hit.document_version_id,
            title=hit.title,
            text=hit.text,
            anchor=hit.anchor,
            ordinal=hit.ordinal,
            score=hit.score,
        )


class SearchResponse(BaseModel):
    query: str
    hits: list[SearchHitRead]


class RebuildIndexRequest(BaseModel):
    run_inline: bool = Field(default=False)


def enqueue_rebuild_index(job: Job) -> None:
    rebuild_domain_index_job.delay(job.id)


@router.post(
    "/domains/{domain_id}/index/rebuild",
    response_model=JobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def rebuild_index(
    payload: RebuildIndexRequest,
    actor: AdminSubjectDep,
    settings: SettingsDep,
    uow: UnitOfWorkDep,
    domain_id: Annotated[str, Path(min_length=1)],
) -> JobRead:
    async with uow:
        domain = await uow.domains.get(domain_id)
        if domain is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain not found")

        job = await uow.jobs.add(
            kind="index.domain",
            status="queued",
            domain_id=domain_id,
            source_id=None,
            payload={"requested_at": datetime.now().isoformat()},
        )
        await uow.journal_events.add(
            actor=actor,
            event_type="index.queued",
            entity_type="job",
            entity_id=job.id,
            payload={"domain_id": domain_id},
        )
        await uow.progress_events.add(
            job_id=job.id,
            event_type="index.queued",
            message=f"Queued BM25 index rebuild for {domain.slug}",
            payload={"domain_id": domain_id, "domain_slug": domain.slug},
        )
        await uow.commit()

    progress_store.append("index.queued", {"job_id": job.id, "domain_id": domain_id})
    if payload.run_inline or settings.env == "test":
        await rebuild_domain_index(
            job_id=job.id,
            uow=uow,
            index=TantivySearchIndex(settings.index_root),
            actor=actor,
        )
        async with uow:
            completed = await uow.jobs.get(job.id)
        if completed is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        return JobRead.from_job(completed)

    enqueue_rebuild_index(job)
    return JobRead.from_job(job)


@router.get("/domains/{domain_id}/search", response_model=SearchResponse)
async def search_domain(
    _: ViewerSubjectDep,
    settings: SettingsDep,
    uow: UnitOfWorkDep,
    domain_id: Annotated[str, Path(min_length=1)],
    q: Annotated[str, Query(min_length=1, max_length=500)],
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> SearchResponse:
    async with uow:
        domain = await uow.domains.get(domain_id)
    if domain is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain not found")

    try:
        hits = TantivySearchIndex(settings.index_root).search_domain(domain_id, q, limit=limit)
    except SearchIndexMissingError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Search index has not been built for this domain",
        ) from exc

    return SearchResponse(query=q, hits=[SearchHitRead.from_hit(hit) for hit in hits])
