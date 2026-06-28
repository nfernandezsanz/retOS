from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query, status
from pydantic import BaseModel, Field

from retos.api.dependencies import (
    AdminSubjectDep,
    SettingsDep,
    UnitOfWorkDep,
    ViewerSubjectDep,
    ensure_domain_access,
)
from retos.api.routes.events import progress_store
from retos.domain.jobs import Job, JobKind, JobStatus
from retos.jobs.tasks import (
    agent_query_job,
    ingest_file_upload_job,
    ingest_text_job,
    rebuild_domain_index_job,
    scan_source_job,
)

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


class JobTransitionRequest(BaseModel):
    error: str | None = Field(default=None, max_length=4000)


class RetryDispatchPlan(BaseModel):
    task_name: str


TRANSITIONS: dict[JobStatus, tuple[JobStatus, ...]] = {
    "queued": ("running", "cancelled"),
    "running": ("succeeded", "failed", "cancelled"),
    "succeeded": (),
    "failed": (),
    "cancelled": (),
}


def retry_dispatch_plan(job: Job) -> RetryDispatchPlan:
    if job.kind == "index.domain":
        if job.domain_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Index retry requires domain_id",
            )
        return RetryDispatchPlan(task_name="rebuild_domain_index")

    if job.kind == "agent.query":
        if job.domain_id is None or not str(job.payload.get("question") or "").strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Agent query retry requires domain_id and question",
            )
        return RetryDispatchPlan(task_name="agent_query")

    if job.kind == "ingest.source":
        ingestion_kind = job.payload.get("ingestion_kind")
        if ingestion_kind == "file_upload":
            if not isinstance(job.payload.get("file_path"), str):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="File upload retry requires file_path",
                )
            return RetryDispatchPlan(task_name="ingest_file_upload")
        if ingestion_kind == "source_scan":
            if job.domain_id is None or job.source_id is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Source scan retry requires domain_id and source_id",
                )
            return RetryDispatchPlan(task_name="scan_source")
        if isinstance(job.payload.get("text"), str) and isinstance(job.payload.get("title"), str):
            if job.domain_id is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Text ingestion retry requires domain_id",
                )
            return RetryDispatchPlan(task_name="ingest_text")

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=f"Job kind {job.kind} cannot be retried by the generic job API",
    )


def dispatch_retry_job(job: Job, plan: RetryDispatchPlan) -> None:
    if plan.task_name == "rebuild_domain_index":
        rebuild_domain_index_job.delay(job.id)
    elif plan.task_name == "agent_query":
        agent_query_job.delay(job.id)
    elif plan.task_name == "ingest_file_upload":
        ingest_file_upload_job.delay(job.id)
    elif plan.task_name == "scan_source":
        scan_source_job.delay(job.id)
    elif plan.task_name == "ingest_text":
        ingest_text_job.delay(job.id)
    else:
        raise RuntimeError(f"Unsupported retry dispatch task: {plan.task_name}")


def validate_transition(current: JobStatus, target: JobStatus) -> None:
    if target not in TRANSITIONS[current]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot transition job from {current} to {target}",
        )


async def transition_job(
    *,
    job_id: str,
    target: JobStatus,
    actor: str,
    uow: UnitOfWorkDep,
    error: str | None = None,
) -> JobRead:
    now = datetime.now(UTC)
    async with uow:
        current = await uow.jobs.get(job_id)
        if current is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        validate_transition(current.status, target)
        job = await uow.jobs.update_status(
            job_id=job_id,
            status=target,
            started_at=now if target == "running" else None,
            completed_at=now if target in ("succeeded", "failed", "cancelled") else None,
            error=error if target == "failed" else None,
        )
        if job is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        event_type = f"job.{target}"
        await uow.journal_events.add(
            actor=actor,
            event_type=event_type,
            entity_type="job",
            entity_id=job.id,
            payload={
                "from_status": current.status,
                "to_status": target,
                "error": job.error,
            },
        )
        await uow.progress_events.add(
            job_id=job.id,
            event_type=event_type,
            message=f"Job {job.kind} is {target}",
            payload={"status": target, "error": job.error},
        )
        await uow.commit()

    progress_store.append(
        f"job.{target}",
        {
            "job_id": job.id,
            "kind": job.kind,
            "status": job.status,
            "error": job.error,
        },
    )
    return JobRead.from_job(job)


@router.post("/{job_id}/retry", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED)
async def retry_job(
    actor: AdminSubjectDep,
    settings: SettingsDep,
    uow: UnitOfWorkDep,
    job_id: Annotated[str, Path(min_length=1)],
) -> JobRead:
    now = datetime.now(UTC)
    async with uow:
        original = await uow.jobs.get(job_id)
        if original is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        if original.status not in {"failed", "cancelled"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot retry job from {original.status}",
            )
        plan = retry_dispatch_plan(original)
        if original.domain_id is not None and await uow.domains.get(original.domain_id) is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain not found")
        if original.source_id is not None:
            source = await uow.sources.get(original.source_id)
            if source is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Source not found"
                )
            if original.domain_id is not None and source.domain_id != original.domain_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Source does not belong to domain",
                )

        retry_payload = {
            **original.payload,
            "retried_from_job_id": original.id,
            "retry_requested_at": now.isoformat(),
        }
        job = await uow.jobs.add(
            kind=original.kind,
            status="queued",
            domain_id=original.domain_id,
            source_id=original.source_id,
            payload=retry_payload,
        )
        await uow.journal_events.add(
            actor=actor,
            event_type="job.retry_queued",
            entity_type="job",
            entity_id=job.id,
            payload={
                "from_job_id": original.id,
                "kind": job.kind,
                "dispatch_task": plan.task_name,
            },
        )
        await uow.progress_events.add(
            job_id=job.id,
            event_type="job.retry_queued",
            message=f"Queued retry for {job.kind}",
            payload={
                "from_job_id": original.id,
                "dispatch_task": plan.task_name,
                "status": job.status,
            },
        )
        await uow.commit()

    if settings.env != "test":
        dispatch_retry_job(job, plan)
    progress_store.append(
        "job.retry_queued",
        {
            "job_id": job.id,
            "from_job_id": original.id,
            "kind": job.kind,
            "status": job.status,
        },
    )
    return JobRead.from_job(job)


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
    actor: ViewerSubjectDep,
    uow: UnitOfWorkDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[JobRead]:
    async with uow:
        admin = await uow.admin_users.get_by_email(actor)
        if admin is not None and "admin" in admin.roles:
            jobs = await uow.jobs.list(limit=limit)
        elif admin is not None:
            jobs = await uow.jobs.list_for_admin_user(admin_user_id=admin.id, limit=limit)
        else:
            jobs = []
    return [JobRead.from_job(job) for job in jobs]


@router.get("/{job_id}", response_model=JobRead)
async def get_job(
    actor: ViewerSubjectDep,
    uow: UnitOfWorkDep,
    job_id: Annotated[str, Path(min_length=1)],
) -> JobRead:
    async with uow:
        job = await uow.jobs.get(job_id)
        if job is not None and job.domain_id is not None:
            await ensure_domain_access(actor=actor, domain_id=job.domain_id, uow=uow)
        elif job is not None:
            admin = await uow.admin_users.get_by_email(actor)
            if admin is None or "admin" not in admin.roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Domain access required",
                )
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return JobRead.from_job(job)


@router.post("/{job_id}/start", response_model=JobRead)
async def start_job(
    actor: AdminSubjectDep,
    uow: UnitOfWorkDep,
    job_id: Annotated[str, Path(min_length=1)],
) -> JobRead:
    return await transition_job(job_id=job_id, target="running", actor=actor, uow=uow)


@router.post("/{job_id}/complete", response_model=JobRead)
async def complete_job(
    actor: AdminSubjectDep,
    uow: UnitOfWorkDep,
    job_id: Annotated[str, Path(min_length=1)],
) -> JobRead:
    return await transition_job(job_id=job_id, target="succeeded", actor=actor, uow=uow)


@router.post("/{job_id}/fail", response_model=JobRead)
async def fail_job(
    payload: JobTransitionRequest,
    actor: AdminSubjectDep,
    uow: UnitOfWorkDep,
    job_id: Annotated[str, Path(min_length=1)],
) -> JobRead:
    return await transition_job(
        job_id=job_id,
        target="failed",
        actor=actor,
        uow=uow,
        error=payload.error or "Job failed",
    )


@router.post("/{job_id}/cancel", response_model=JobRead)
async def cancel_job(
    actor: AdminSubjectDep,
    uow: UnitOfWorkDep,
    job_id: Annotated[str, Path(min_length=1)],
) -> JobRead:
    return await transition_job(job_id=job_id, target="cancelled", actor=actor, uow=uow)
