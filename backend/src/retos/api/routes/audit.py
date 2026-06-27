from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from retos.api.dependencies import AdminSubjectDep, UnitOfWorkDep
from retos.domain.jobs import JournalEvent, ProgressEvent

router = APIRouter(prefix="/audit", tags=["audit"])


class JournalEventRead(BaseModel):
    id: str
    occurred_at: datetime
    actor: str
    event_type: str
    entity_type: str
    entity_id: str
    payload: dict[str, Any]

    @classmethod
    def from_event(cls, event: JournalEvent) -> JournalEventRead:
        return cls(
            id=event.id,
            occurred_at=event.occurred_at,
            actor=event.actor,
            event_type=event.event_type,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            payload=event.payload,
        )


class ProgressEventRead(BaseModel):
    id: str
    job_id: str | None
    occurred_at: datetime
    event_type: str
    message: str
    payload: dict[str, Any]

    @classmethod
    def from_event(cls, event: ProgressEvent) -> ProgressEventRead:
        return cls(
            id=event.id,
            job_id=event.job_id,
            occurred_at=event.occurred_at,
            event_type=event.event_type,
            message=event.message,
            payload=event.payload,
        )


class AuditExportRead(BaseModel):
    schema_version: str
    generated_at: datetime
    limit: int
    journal_events: list[JournalEventRead]
    progress_events: list[ProgressEventRead]


@router.get("/journal-events", response_model=list[JournalEventRead])
async def list_journal_events(
    _: AdminSubjectDep,
    uow: UnitOfWorkDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[JournalEventRead]:
    async with uow:
        events = await uow.journal_events.list(limit=limit)
    return [JournalEventRead.from_event(event) for event in events]


@router.get("/progress-events", response_model=list[ProgressEventRead])
async def list_progress_events(
    _: AdminSubjectDep,
    uow: UnitOfWorkDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[ProgressEventRead]:
    async with uow:
        events = await uow.progress_events.list(limit=limit)
    return [ProgressEventRead.from_event(event) for event in events]


@router.get("/export", response_model=AuditExportRead)
async def export_audit_events(
    _: AdminSubjectDep,
    uow: UnitOfWorkDep,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> JSONResponse:
    async with uow:
        journal_events = await uow.journal_events.list(limit=limit)
        progress_events = await uow.progress_events.list(limit=limit)

    payload = AuditExportRead(
        schema_version="retos.audit-export.v1",
        generated_at=datetime.now(UTC),
        limit=limit,
        journal_events=[JournalEventRead.from_event(event) for event in journal_events],
        progress_events=[ProgressEventRead.from_event(event) for event in progress_events],
    )
    return JSONResponse(
        content=payload.model_dump(mode="json"),
        headers={
            "Content-Disposition": 'attachment; filename="retos-audit-export.json"',
            "Cache-Control": "no-store",
        },
    )
