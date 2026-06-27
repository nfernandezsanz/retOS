import pytest
from fastapi.testclient import TestClient

from retos.api.routes.events import InMemoryProgressStore, event_stream, parse_last_event_id


def test_parse_last_event_id() -> None:
    assert parse_last_event_id(None) is None
    assert parse_last_event_id("") is None
    assert parse_last_event_id("abc") is None
    assert parse_last_event_id("-1") is None
    assert parse_last_event_id("12") == 12


def test_progress_stream_requires_auth(client: TestClient) -> None:
    response = client.get("/events/progress")

    assert response.status_code == 401


def test_progress_store_returns_recent_and_incremental_events() -> None:
    store = InMemoryProgressStore()
    second = store.append("job.started", {"job_id": "abc"})
    third = store.append("job.completed", {"job_id": "abc"})

    assert [event.id for event in store.since(None)] == [1, 2, 3]
    assert store.since(second.id) == [third]


@pytest.mark.asyncio
async def test_event_stream_yields_progress_event() -> None:
    class Request:
        def __init__(self) -> None:
            self.calls = 0

        async def is_disconnected(self) -> bool:
            self.calls += 1
            return self.calls > 1

    stream = event_stream(Request(), None)  # type: ignore[arg-type]
    event = await anext(stream)

    assert event["event"] == "system.ready"
    assert event["id"] == "1"
