import pytest
from fastapi.testclient import TestClient

from retos.api.routes.events import (
    InMemoryProgressStore,
    event_stream,
    parse_last_event_id,
    persisted_event_id,
)
from retos.persistence.unit_of_work import SQLAlchemyUnitOfWork


def test_parse_last_event_id() -> None:
    assert parse_last_event_id(None) is None
    assert parse_last_event_id("") is None
    assert parse_last_event_id("abc") is None
    assert parse_last_event_id("-1") is None
    assert parse_last_event_id("12") == "live:12"
    assert parse_last_event_id("live:12") == "live:12"
    assert parse_last_event_id("progress:event-1") == "progress:event-1"


def test_persisted_event_id_extracts_progress_cursor() -> None:
    assert persisted_event_id(None) is None
    assert persisted_event_id("live:3") is None
    assert persisted_event_id("progress:event-1") == "event-1"


def test_progress_stream_requires_auth(client: TestClient) -> None:
    response = client.get("/events/progress")

    assert response.status_code == 401


def test_progress_store_returns_recent_and_incremental_events() -> None:
    store = InMemoryProgressStore()
    second = store.append("job.started", {"job_id": "abc"})
    third = store.append("job.completed", {"job_id": "abc"})

    assert [event.id for event in store.since(None)] == ["live:1", "live:2", "live:3"]
    assert store.since(second.id) == [third]
    assert store.since("progress:persisted") == []


@pytest.mark.asyncio
async def test_event_stream_yields_progress_event(client: TestClient) -> None:
    class Request:
        def __init__(self) -> None:
            self.calls = 0

        async def is_disconnected(self) -> bool:
            self.calls += 1
            return self.calls > 1

    stream = event_stream(Request(), None, SQLAlchemyUnitOfWork(client.app.state.session_factory))  # type: ignore[arg-type]
    event = await anext(stream)

    assert event["event"] == "system.ready"
    assert event["id"] == "live:1"


@pytest.mark.asyncio
async def test_event_stream_replays_persisted_progress_events(client: TestClient) -> None:
    login = client.post(
        "/auth/login",
        json={"email": "admin@retos.dev", "password": "test-admin-password"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    domain = client.post(
        "/domains",
        headers=headers,
        json={"slug": "events-replay", "name": "Events Replay"},
    )
    job = client.post(
        "/jobs",
        headers=headers,
        json={
            "kind": "index.domain",
            "domain_id": domain.json()["id"],
            "payload": {"reason": "events-test"},
        },
    )
    job_id = job.json()["id"]

    class Request:
        def __init__(self) -> None:
            self.calls = 0

        async def is_disconnected(self) -> bool:
            self.calls += 1
            return self.calls > 5

    stream = event_stream(
        Request(),  # type: ignore[arg-type]
        None,
        SQLAlchemyUnitOfWork(client.app.state.session_factory),
    )
    events = [await anext(stream) for _ in range(3)]

    assert any(event["id"].startswith("progress:") for event in events)
    assert any(event["event"] == "job.queued" and job_id in event["data"] for event in events)


@pytest.mark.asyncio
async def test_event_stream_continues_live_events_after_progress_cursor(
    client: TestClient,
) -> None:
    class Request:
        def __init__(self) -> None:
            self.calls = 0

        async def is_disconnected(self) -> bool:
            self.calls += 1
            return self.calls > 3

    stream = event_stream(
        Request(),  # type: ignore[arg-type]
        "progress:missing-progress-event",
        SQLAlchemyUnitOfWork(client.app.state.session_factory),
    )
    event = await anext(stream)

    assert event["id"].startswith("live:")


@pytest.mark.asyncio
async def test_progress_event_repository_lists_chronological_and_after(
    client: TestClient,
) -> None:
    login = client.post(
        "/auth/login",
        json={"email": "admin@retos.dev", "password": "test-admin-password"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    first_domain = client.post(
        "/domains",
        headers=headers,
        json={"slug": "events-repository-first", "name": "Events Repository First"},
    )
    second_domain = client.post(
        "/domains",
        headers=headers,
        json={"slug": "events-repository-second", "name": "Events Repository Second"},
    )
    first_job = client.post(
        "/jobs",
        headers=headers,
        json={
            "kind": "index.domain",
            "domain_id": first_domain.json()["id"],
            "payload": {"order": 1},
        },
    )
    second_job = client.post(
        "/jobs",
        headers=headers,
        json={
            "kind": "index.domain",
            "domain_id": second_domain.json()["id"],
            "payload": {"order": 2},
        },
    )

    async with SQLAlchemyUnitOfWork(client.app.state.session_factory) as uow:
        chronological = await uow.progress_events.list_chronological(limit=10)
        after_first = await uow.progress_events.list_after(
            event_id=chronological[0].id,
            limit=10,
        )
        after_missing = await uow.progress_events.list_after(
            event_id="missing-progress-event",
            limit=2,
        )

    assert chronological[0].occurred_at <= chronological[-1].occurred_at
    assert any(event.job_id == first_job.json()["id"] for event in chronological)
    assert any(event.job_id == second_job.json()["id"] for event in after_first)
    assert len(after_missing) == 2
