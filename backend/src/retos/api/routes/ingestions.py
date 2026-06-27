from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, status
from pydantic import BaseModel, Field

from retos.api.dependencies import AdminSubjectDep, SettingsDep, UnitOfWorkDep
from retos.api.routes.events import progress_store
from retos.api.routes.jobs import JobRead
from retos.domain.jobs import Job
from retos.jobs.tasks import ingest_text_job, scan_source_job

router = APIRouter(tags=["ingestions"])


class TextIngestionCreate(BaseModel):
    source_id: str | None = Field(default=None, min_length=1, max_length=36)
    title: str = Field(min_length=1, max_length=255)
    text: str = Field(min_length=1, max_length=500_000)
    source_uri: str | None = Field(default=None, min_length=1, max_length=4000)
    external_id: str | None = Field(default=None, max_length=255)
    metadata: dict[str, Any] = Field(default_factory=dict)
    max_segment_tokens: int = Field(default=220, ge=20, le=1000)


class SourceScanCreate(BaseModel):
    run_inline: bool = Field(default=False)
    max_files: int = Field(default=500, ge=1, le=10_000)
    max_bytes: int = Field(default=2_000_000, ge=1, le=50_000_000)
    max_segment_tokens: int = Field(default=220, ge=20, le=1000)
    enable_ocr: bool = True
    max_ocr_pages: int = Field(default=20, ge=1, le=500)


def enqueue_text_ingestion(job: Job) -> None:
    ingest_text_job.delay(job.id)


def enqueue_source_scan(job: Job) -> None:
    scan_source_job.delay(job.id)


@router.post(
    "/domains/{domain_id}/ingestions/text",
    response_model=JobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_text_ingestion(
    payload: TextIngestionCreate,
    actor: AdminSubjectDep,
    settings: SettingsDep,
    uow: UnitOfWorkDep,
    domain_id: Annotated[str, Path(min_length=1)],
) -> JobRead:
    async with uow:
        domain = await uow.domains.get(domain_id)
        if domain is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain not found")
        if payload.source_id is not None:
            source = await uow.sources.get(payload.source_id)
            if source is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Source not found",
                )
            if source.domain_id != domain_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Source does not belong to domain",
                )

        job = await uow.jobs.add(
            kind="ingest.source",
            status="queued",
            domain_id=domain_id,
            source_id=payload.source_id,
            payload=payload.model_dump(),
        )
        await uow.journal_events.add(
            actor=actor,
            event_type="ingestion.queued",
            entity_type="job",
            entity_id=job.id,
            payload={
                "kind": "text",
                "domain_id": domain_id,
                "source_id": payload.source_id,
                "title": payload.title,
            },
        )
        await uow.progress_events.add(
            job_id=job.id,
            event_type="ingestion.queued",
            message=f"Queued text ingestion for {payload.title}",
            payload={"title": payload.title, "domain_id": domain_id},
        )
        await uow.commit()

    if settings.env != "test":
        enqueue_text_ingestion(job)
    progress_store.append(
        "ingestion.queued",
        {"job_id": job.id, "domain_id": domain_id, "title": payload.title},
    )
    return JobRead.from_job(job)


@router.post(
    "/sources/{source_id}/scan",
    response_model=JobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def scan_source(
    payload: SourceScanCreate,
    actor: AdminSubjectDep,
    settings: SettingsDep,
    uow: UnitOfWorkDep,
    source_id: Annotated[str, Path(min_length=1)],
) -> JobRead:
    async with uow:
        source = await uow.sources.get(source_id)
        if source is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
        if source.kind != "mount":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Source scan currently supports mount sources only",
            )
        job = await uow.jobs.add(
            kind="ingest.source",
            status="queued",
            domain_id=source.domain_id,
            source_id=source.id,
            payload={
                "ingestion_kind": "source_scan",
                "max_files": payload.max_files,
                "max_bytes": payload.max_bytes,
                "max_segment_tokens": payload.max_segment_tokens,
                "enable_ocr": payload.enable_ocr,
                "max_ocr_pages": payload.max_ocr_pages,
            },
        )
        await uow.journal_events.add(
            actor=actor,
            event_type="scan.queued",
            entity_type="job",
            entity_id=job.id,
            payload={
                "source_id": source.id,
                "domain_id": source.domain_id,
                "uri": source.uri,
            },
        )
        await uow.progress_events.add(
            job_id=job.id,
            event_type="scan.queued",
            message=f"Queued source scan for {source.name}",
            payload={"source_id": source.id, "domain_id": source.domain_id},
        )
        await uow.commit()

    if payload.run_inline or settings.env == "test":
        from retos.ingestion.scan import run_source_scan

        await run_source_scan(job_id=job.id, uow=uow, actor=actor)
        async with uow:
            completed = await uow.jobs.get(job.id)
        if completed is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        return JobRead.from_job(completed)

    enqueue_source_scan(job)
    progress_store.append(
        "scan.queued",
        {"job_id": job.id, "source_id": source.id, "domain_id": source.domain_id},
    )
    return JobRead.from_job(job)
