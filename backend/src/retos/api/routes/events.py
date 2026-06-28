import asyncio
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from retos.api.dependencies import UnitOfWorkDep, ViewerSubjectDep, visible_domain_ids_for_actor
from retos.domain.jobs import ProgressEvent as PersistedProgressEvent
from retos.persistence.unit_of_work import SQLAlchemyUnitOfWork

router = APIRouter(prefix="/events", tags=["events"])
LIVE_EVENT_PREFIX = "live:"
PERSISTED_EVENT_PREFIX = "progress:"
PERSISTED_REPLAY_LIMIT = 50


class ProgressEvent(BaseModel):
    id: str = Field(min_length=1)
    event: str
    data: dict[str, Any]


class InMemoryProgressStore:
    def __init__(self) -> None:
        self._events: list[ProgressEvent] = []
        self.reset()

    def reset(self) -> None:
        self._events = [
            ProgressEvent(
                id=f"{LIVE_EVENT_PREFIX}1",
                event="system.ready",
                data={"message": "RetOS API is ready"},
            )
        ]

    def append(self, event: str, data: dict[str, str | int | float | bool | None]) -> ProgressEvent:
        item = ProgressEvent(
            id=f"{LIVE_EVENT_PREFIX}{len(self._events) + 1}", event=event, data=data
        )
        self._events.append(item)
        return item

    def since(self, last_event_id: str | None) -> list[ProgressEvent]:
        if last_event_id is None:
            return self._events[-10:]
        last_live_number = live_event_number(last_event_id)
        if last_live_number is None:
            return []
        return [
            event for event in self._events if (live_event_number(event.id) or 0) > last_live_number
        ]


progress_store = InMemoryProgressStore()


def parse_last_event_id(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    if value.startswith((LIVE_EVENT_PREFIX, PERSISTED_EVENT_PREFIX)):
        return value
    parsed = live_event_number(value)
    if parsed is None:
        return None
    return f"{LIVE_EVENT_PREFIX}{parsed}"


def live_event_number(value: str) -> int | None:
    candidate = value.removeprefix(LIVE_EVENT_PREFIX)
    try:
        parsed = int(candidate)
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def persisted_event_id(last_event_id: str | None) -> str | None:
    if last_event_id is None or not last_event_id.startswith(PERSISTED_EVENT_PREFIX):
        return None
    return last_event_id.removeprefix(PERSISTED_EVENT_PREFIX) or None


def persisted_to_stream_event(event: PersistedProgressEvent) -> ProgressEvent:
    return ProgressEvent(
        id=f"{PERSISTED_EVENT_PREFIX}{event.id}",
        event=event.event_type,
        data={
            "job_id": event.job_id,
            "occurred_at": event.occurred_at.isoformat(),
            "message": event.message,
            "payload": event.payload,
        },
    )


async def persisted_replay_events(
    *,
    uow: SQLAlchemyUnitOfWork,
    actor: str,
    last_event_id: str | None,
) -> list[ProgressEvent]:
    async with uow:
        visible_domain_ids = await visible_domain_ids_for_actor(actor=actor, uow=uow)
        persisted_id = persisted_event_id(last_event_id)
        if visible_domain_ids is not None and persisted_id is not None:
            events = await uow.progress_events.list_after_for_domain_ids(
                event_id=persisted_id,
                domain_ids=visible_domain_ids,
                limit=PERSISTED_REPLAY_LIMIT,
            )
        elif visible_domain_ids is not None:
            events = await uow.progress_events.list_chronological_for_domain_ids(
                domain_ids=visible_domain_ids,
                limit=PERSISTED_REPLAY_LIMIT,
            )
        elif persisted_id is not None:
            events = await uow.progress_events.list_after(
                event_id=persisted_id,
                limit=PERSISTED_REPLAY_LIMIT,
            )
        else:
            events = await uow.progress_events.list_chronological(limit=PERSISTED_REPLAY_LIMIT)
    return [persisted_to_stream_event(event) for event in events]


async def live_event_visible_to_actor(
    *,
    item: ProgressEvent,
    actor: str,
    uow: SQLAlchemyUnitOfWork,
) -> bool:
    if item.event == "system.ready":
        return True
    async with uow:
        visible_domain_ids = await visible_domain_ids_for_actor(actor=actor, uow=uow)
        if visible_domain_ids is None:
            return True
        domain_id = item.data.get("domain_id")
        if isinstance(domain_id, str) and domain_id in visible_domain_ids:
            return True
        job_id = item.data.get("job_id")
        if isinstance(job_id, str):
            job = await uow.jobs.get(job_id)
            return job is not None and job.domain_id in visible_domain_ids
    return False


async def event_stream(
    request: Request,
    actor: str,
    last_event_id: str | None,
    uow: SQLAlchemyUnitOfWork,
) -> AsyncIterator[dict[str, str]]:
    replayed = await persisted_replay_events(uow=uow, actor=actor, last_event_id=last_event_id)
    for item in replayed:
        if await request.is_disconnected():
            return
        yield {
            "id": item.id,
            "event": item.event,
            "data": item.model_dump_json(),
        }

    next_id = last_event_id if live_event_number(last_event_id or "") is not None else None
    while not await request.is_disconnected():
        for item in progress_store.since(next_id):
            next_id = item.id
            if not await live_event_visible_to_actor(item=item, actor=actor, uow=uow):
                continue
            yield {
                "id": str(item.id),
                "event": item.event,
                "data": item.model_dump_json(),
            }
        await asyncio.sleep(1)


@router.get("/progress")
async def progress_events(
    request: Request,
    actor: ViewerSubjectDep,
    uow: UnitOfWorkDep,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> EventSourceResponse:
    return EventSourceResponse(
        event_stream(request, actor, parse_last_event_id(last_event_id), uow),
        ping=15,
        headers={"Cache-Control": "no-store"},
    )
