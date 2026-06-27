import asyncio
from collections.abc import AsyncIterator

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from retos.api.dependencies import AdminSubjectDep

router = APIRouter(prefix="/events", tags=["events"])


class ProgressEvent(BaseModel):
    id: int = Field(ge=1)
    event: str
    data: dict[str, str | int | float | bool | None]


class InMemoryProgressStore:
    def __init__(self) -> None:
        self._events: list[ProgressEvent] = []
        self.reset()

    def reset(self) -> None:
        self._events = [
            ProgressEvent(
                id=1,
                event="system.ready",
                data={"message": "RetOS API is ready"},
            )
        ]

    def append(self, event: str, data: dict[str, str | int | float | bool | None]) -> ProgressEvent:
        item = ProgressEvent(id=len(self._events) + 1, event=event, data=data)
        self._events.append(item)
        return item

    def since(self, last_event_id: int | None) -> list[ProgressEvent]:
        if last_event_id is None:
            return self._events[-10:]
        return [event for event in self._events if event.id > last_event_id]


progress_store = InMemoryProgressStore()


def parse_last_event_id(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed > 0 else None


async def event_stream(
    request: Request,
    last_event_id: int | None,
) -> AsyncIterator[dict[str, str]]:
    next_id = last_event_id
    while not await request.is_disconnected():
        for item in progress_store.since(next_id):
            next_id = item.id
            yield {
                "id": str(item.id),
                "event": item.event,
                "data": item.model_dump_json(),
            }
        await asyncio.sleep(1)


@router.get("/progress")
async def progress_events(
    request: Request,
    _: AdminSubjectDep,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> EventSourceResponse:
    return EventSourceResponse(
        event_stream(request, parse_last_event_id(last_event_id)),
        ping=15,
        headers={"Cache-Control": "no-store"},
    )
