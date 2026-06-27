from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query, status
from pydantic import BaseModel, Field

from retos.api.dependencies import AdminSubjectDep, UnitOfWorkDep
from retos.api.routes.events import progress_store
from retos.domain.jobs import Job, JobKind, JobStatus

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobCreate(BaseModel):
    kind: JobKind
    domain_id: str | None = Field(default=None, min_length=1, max_length=36)
    source_id: str | None = Field(default=None, min_length=1, max_length=36)
    payload: dict[str, Any] = Field(default_factory=dict)


class JobRead(BaseModel):
    id: str
    kind: JobKind
    status: JobStatus
    domain_id: str | None
    source_id: str | None
    payload: dict[str, Any]
    error: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_job(cls, job: Job) -> JobRead:
        return cls(
            id=job.id,
            kind=job.kind,
            status=job.status,
            domain_id=job.domain_id,
            source_id=job.source_id,
            payload=job.payload,
            error=job.error,
            started_at=job.started_at,
            completed_at=job.completed_at,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )


@router.post("", response_model=JobRead, status_code=status.HTTP_201_CREATED)
async def create_job(
    payload: JobCreate,
    actor: AdminSubjectDep,
    uow: UnitOfWorkDep,
) -> JobRead:
    async with uow:
        if payload.domain_id is not None:
            domain = await uow.domains.get(payload.domain_id)
            if domain is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Domain not found",
                )
        if payload.source_id is not None:
            source = await uow.sources.get(payload.source_id)
            if source is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Source not found",
                )
            if payload.domain_id is not None and source.domain_id != payload.domain_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Source does not belong to domain",
                )

        job = await uow.jobs.add(
            kind=payload.kind,
            status="queued",
            domain_id=payload.domain_id,
            source_id=payload.source_id,
            payload=payload.payload,
        )
        await uow.journal_events.add(
            actor=actor,
            event_type="job.created",
            entity_type="job",
            entity_id=job.id,
            payload={
                "kind": job.kind,
                "status": job.status,
                "domain_id": job.domain_id,
                "source_id": job.source_id,
            },
        )
        await uow.progress_events.add(
            job_id=job.id,
            event_type="job.queued",
            message=f"Queued {job.kind}",
            payload={"status": job.status},
        )
        await uow.commit()

    progress_store.append(
        "job.queued",
        {
            "job_id": job.id,
            "kind": job.kind,
            "status": job.status,
        },
    )
    return JobRead.from_job(job)


@router.get("", response_model=list[JobRead])
async def list_jobs(
    _: AdminSubjectDep,
    uow: UnitOfWorkDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[JobRead]:
    async with uow:
        jobs = await uow.jobs.list(limit=limit)
    return [JobRead.from_job(job) for job in jobs]


@router.get("/{job_id}", response_model=JobRead)
async def get_job(
    _: AdminSubjectDep,
    uow: UnitOfWorkDep,
    job_id: Annotated[str, Path(min_length=1)],
) -> JobRead:
    async with uow:
        job = await uow.jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return JobRead.from_job(job)
