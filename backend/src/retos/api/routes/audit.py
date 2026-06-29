from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from retos.api.dependencies import UnitOfWorkDep, ViewerSubjectDep, visible_domain_ids_for_actor
from retos.core.audit_hash import (
    AUDIT_HASH_ALGORITHM,
    AUDIT_HASH_CANONICALIZATION,
    audit_event_hash,
    audit_payload_hash,
)
from retos.domain.jobs import JournalEvent, ProgressEvent

router = APIRouter(prefix="/audit", tags=["audit"])


class JournalEventRead(BaseModel):
    id: str
    trace_id: str | None
    payload_hash: str | None
    prev_hash: str | None
    event_hash: str | None
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
            trace_id=event.trace_id,
            payload_hash=event.payload_hash,
            prev_hash=event.prev_hash,
            event_hash=event.event_hash,
            occurred_at=event.occurred_at,
            actor=event.actor,
            event_type=event.event_type,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            payload=event.payload,
        )


class ProgressEventRead(BaseModel):
    id: str
    trace_id: str | None
    payload_hash: str | None
    prev_hash: str | None
    event_hash: str | None
    job_id: str | None
    occurred_at: datetime
    event_type: str
    message: str
    payload: dict[str, Any]

    @classmethod
    def from_event(cls, event: ProgressEvent) -> ProgressEventRead:
        return cls(
            id=event.id,
            trace_id=event.trace_id,
            payload_hash=event.payload_hash,
            prev_hash=event.prev_hash,
            event_hash=event.event_hash,
            job_id=event.job_id,
            occurred_at=event.occurred_at,
            event_type=event.event_type,
            message=event.message,
            payload=event.payload,
        )


class AuditHashChainEntryRead(BaseModel):
    event_id: str
    trace_id: str | None
    event_stream: str
    event_type: str
    occurred_at: datetime
    payload_hash: str
    prev_hash: str | None
    event_hash: str


class AuditExportIntegrityRead(BaseModel):
    algorithm: str
    canonicalization: str
    valid: bool
    event_count: int
    head_hash: str | None
    chain: list[AuditHashChainEntryRead]


class AuditExportRead(BaseModel):
    schema_version: str
    generated_at: datetime
    limit: int
    journal_events: list[JournalEventRead]
    progress_events: list[ProgressEventRead]
    integrity: AuditExportIntegrityRead


def build_audit_integrity(
    *,
    journal_events: list[JournalEvent],
    progress_events: list[ProgressEvent],
) -> AuditExportIntegrityRead:
    entries: list[AuditHashChainEntryRead] = []
    prev_hash: str | None = None
    chronological = sorted(
        [
            (
                "journal",
                event.id,
                event.trace_id,
                event.occurred_at,
                event.event_type,
                event.payload,
                event.payload_hash,
                event.prev_hash,
                event.event_hash,
            )
            for event in journal_events
        ]
        + [
            (
                "progress",
                event.id,
                event.trace_id,
                event.occurred_at,
                event.event_type,
                event.payload,
                event.payload_hash,
                event.prev_hash,
                event.event_hash,
            )
            for event in progress_events
        ],
        key=lambda item: (item[3], item[0], item[1]),
    )
    for (
        event_stream,
        event_id,
        trace_id,
        occurred_at,
        event_type,
        payload,
        _stored_payload_hash,
        stored_prev_hash,
        stored_event_hash,
    ) in chronological:
        payload_hash = audit_payload_hash(payload)
        entry_prev_hash = stored_prev_hash if stored_event_hash else prev_hash
        event_hash = stored_event_hash or audit_event_hash(
            event_id=event_id,
            trace_id=trace_id,
            event_stream=event_stream,
            event_type=event_type,
            occurred_at=occurred_at,
            payload_hash=payload_hash,
            prev_hash=entry_prev_hash,
        )
        entries.append(
            AuditHashChainEntryRead(
                event_id=event_id,
                trace_id=trace_id,
                event_stream=event_stream,
                event_type=event_type,
                occurred_at=occurred_at,
                payload_hash=payload_hash,
                prev_hash=entry_prev_hash,
                event_hash=event_hash,
            )
        )
        prev_hash = event_hash
    return AuditExportIntegrityRead(
        algorithm=AUDIT_HASH_ALGORITHM,
        canonicalization=AUDIT_HASH_CANONICALIZATION,
        valid=validate_audit_chain(entries),
        event_count=len(entries),
        head_hash=prev_hash,
        chain=entries,
    )


def validate_audit_chain(entries: list[AuditHashChainEntryRead]) -> bool:
    for entry in entries:
        expected_hash = audit_event_hash(
            event_id=entry.event_id,
            trace_id=entry.trace_id,
            event_stream=entry.event_stream,
            event_type=entry.event_type,
            occurred_at=entry.occurred_at,
            payload_hash=entry.payload_hash,
            prev_hash=entry.prev_hash,
        )
        if entry.event_hash != expected_hash:
            return False
    return True


@router.get("/journal-events", response_model=list[JournalEventRead])
async def list_journal_events(
    actor: ViewerSubjectDep,
    uow: UnitOfWorkDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[JournalEventRead]:
    async with uow:
        visible_domain_ids = await visible_domain_ids_for_actor(actor=actor, uow=uow)
        if visible_domain_ids is None:
            events = await uow.journal_events.list(limit=limit)
        else:
            events = await uow.journal_events.list_for_domain_ids(
                domain_ids=visible_domain_ids,
                limit=limit,
            )
    return [JournalEventRead.from_event(event) for event in events]


@router.get("/progress-events", response_model=list[ProgressEventRead])
async def list_progress_events(
    actor: ViewerSubjectDep,
    uow: UnitOfWorkDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[ProgressEventRead]:
    async with uow:
        visible_domain_ids = await visible_domain_ids_for_actor(actor=actor, uow=uow)
        if visible_domain_ids is None:
            events = await uow.progress_events.list(limit=limit)
        else:
            events = await uow.progress_events.list_for_domain_ids(
                domain_ids=visible_domain_ids,
                limit=limit,
            )
    return [ProgressEventRead.from_event(event) for event in events]


@router.get("/export", response_model=AuditExportRead)
async def export_audit_events(
    actor: ViewerSubjectDep,
    uow: UnitOfWorkDep,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> JSONResponse:
    async with uow:
        visible_domain_ids = await visible_domain_ids_for_actor(actor=actor, uow=uow)
        if visible_domain_ids is None:
            journal_events = await uow.journal_events.list(limit=limit)
            progress_events = await uow.progress_events.list(limit=limit)
        else:
            journal_events = await uow.journal_events.list_for_domain_ids(
                domain_ids=visible_domain_ids,
                limit=limit,
            )
            progress_events = await uow.progress_events.list_for_domain_ids(
                domain_ids=visible_domain_ids,
                limit=limit,
            )

    payload = AuditExportRead(
        schema_version="retos.audit-export.v2",
        generated_at=datetime.now(UTC),
        limit=limit,
        journal_events=[JournalEventRead.from_event(event) for event in journal_events],
        progress_events=[ProgressEventRead.from_event(event) for event in progress_events],
        integrity=build_audit_integrity(
            journal_events=journal_events,
            progress_events=progress_events,
        ),
    )
    return JSONResponse(
        content=payload.model_dump(mode="json"),
        headers={
            "Content-Disposition": 'attachment; filename="retos-audit-export.json"',
            "Cache-Control": "no-store",
        },
    )
