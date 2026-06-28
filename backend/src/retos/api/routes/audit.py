import hashlib
import json
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from retos.api.dependencies import UnitOfWorkDep, ViewerSubjectDep, visible_domain_ids_for_actor
from retos.domain.jobs import JournalEvent, ProgressEvent

router = APIRouter(prefix="/audit", tags=["audit"])


class JournalEventRead(BaseModel):
    id: str
    trace_id: str | None
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


def canonical_json_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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
            )
            for event in progress_events
        ],
        key=lambda item: (item[3], item[0], item[1]),
    )
    for event_stream, event_id, trace_id, occurred_at, event_type, payload in chronological:
        payload_hash = canonical_json_hash(payload)
        event_hash = canonical_json_hash(
            {
                "event_id": event_id,
                "trace_id": trace_id,
                "event_stream": event_stream,
                "event_type": event_type,
                "occurred_at": occurred_at.isoformat(),
                "payload_hash": payload_hash,
                "prev_hash": prev_hash,
            }
        )
        entries.append(
            AuditHashChainEntryRead(
                event_id=event_id,
                trace_id=trace_id,
                event_stream=event_stream,
                event_type=event_type,
                occurred_at=occurred_at,
                payload_hash=payload_hash,
                prev_hash=prev_hash,
                event_hash=event_hash,
            )
        )
        prev_hash = event_hash
    return AuditExportIntegrityRead(
        algorithm="sha256",
        canonicalization="json-sort-keys-v1",
        valid=validate_audit_chain(entries),
        event_count=len(entries),
        head_hash=prev_hash,
        chain=entries,
    )


def validate_audit_chain(entries: list[AuditHashChainEntryRead]) -> bool:
    prev_hash: str | None = None
    for entry in entries:
        expected_hash = canonical_json_hash(
            {
                "event_id": entry.event_id,
                "trace_id": entry.trace_id,
                "event_stream": entry.event_stream,
                "event_type": entry.event_type,
                "occurred_at": entry.occurred_at.isoformat(),
                "payload_hash": entry.payload_hash,
                "prev_hash": prev_hash,
            }
        )
        if entry.prev_hash != prev_hash or entry.event_hash != expected_hash:
            return False
        prev_hash = entry.event_hash
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
