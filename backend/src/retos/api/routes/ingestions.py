from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, status
from pydantic import BaseModel, Field

from retos.api.dependencies import AdminSubjectDep, SettingsDep, UnitOfWorkDep
from retos.api.routes.events import progress_store
from retos.api.routes.jobs import JobRead
from retos.domain.jobs import Job
from retos.jobs.tasks import ingest_text_job

router = APIRouter(tags=["ingestions"])


class TextIngestionCreate(BaseModel):
    source_id: str | None = Field(default=None, min_length=1, max_length=36)
    title: str = Field(min_length=1, max_length=255)
    text: str = Field(min_length=1, max_length=500_000)
    source_uri: str | None = Field(default=None, min_length=1, max_length=4000)
    external_id: str | None = Field(default=None, max_length=255)
    metadata: dict[str, Any] = Field(default_factory=dict)
    max_segment_tokens: int = Field(default=220, ge=20, le=1000)


def enqueue_text_ingestion(job: Job) -> None:
    ingest_text_job.delay(job.id)


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
