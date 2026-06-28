import pytest
from fastapi.testclient import TestClient

from retos.api.routes.events import (
    InMemoryProgressStore,
    ProgressEvent,
    event_stream,
    live_event_visible_to_actor,
    parse_last_event_id,
    persisted_event_id,
    persisted_replay_events,
    progress_store,
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

    stream = event_stream(
        Request(),  # type: ignore[arg-type]
        "admin@retos.dev",
        None,
        SQLAlchemyUnitOfWork(client.app.state.session_factory),
    )
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
        "admin@retos.dev",
        None,
        SQLAlchemyUnitOfWork(client.app.state.session_factory),
    )
    events = [await anext(stream) for _ in range(3)]

    assert any(event["id"].startswith("progress:") for event in events)
    assert any(event["event"] == "job.queued" and job_id in event["data"] for event in events)


@pytest.mark.asyncio
async def test_event_stream_stops_when_disconnected_during_persisted_replay(
    client: TestClient,
) -> None:
    login = client.post(
        "/auth/login",
        json={"email": "admin@retos.dev", "password": "test-admin-password"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    domain = client.post(
        "/domains",
        headers=headers,
        json={"slug": "events-disconnect", "name": "Events Disconnect"},
    )
    client.post(
        "/jobs",
        headers=headers,
        json={"kind": "index.domain", "domain_id": domain.json()["id"], "payload": {}},
    )

    class Request:
        async def is_disconnected(self) -> bool:
            return True

    stream = event_stream(
        Request(),  # type: ignore[arg-type]
        "admin@retos.dev",
        None,
        SQLAlchemyUnitOfWork(client.app.state.session_factory),
    )

    with pytest.raises(StopAsyncIteration):
        await anext(stream)


@pytest.mark.asyncio
async def test_event_stream_replay_is_scoped_for_viewer(client: TestClient) -> None:
    login = client.post(
        "/auth/login",
        json={"email": "admin@retos.dev", "password": "test-admin-password"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    granted_domain = client.post(
        "/domains",
        headers=headers,
        json={"slug": "events-granted", "name": "Events Granted"},
    )
    hidden_domain = client.post(
        "/domains",
        headers=headers,
        json={"slug": "events-hidden", "name": "Events Hidden"},
    )
    granted_job = client.post(
        "/jobs",
        headers=headers,
        json={
            "kind": "index.domain",
            "domain_id": granted_domain.json()["id"],
            "payload": {"reason": "events-granted"},
        },
    )
    hidden_job = client.post(
        "/jobs",
        headers=headers,
        json={
            "kind": "index.domain",
            "domain_id": hidden_domain.json()["id"],
            "payload": {"reason": "events-hidden"},
        },
    )
    viewer = client.post(
        "/admin/users",
        headers=headers,
        json={
            "email": "events-viewer@retos.dev",
            "password": "events-viewer-password",
            "roles": ["viewer"],
        },
    )
    grant = client.post(
        f"/admin/users/{viewer.json()['id']}/domain-grants",
        headers=headers,
        json={"domain_id": granted_domain.json()["id"]},
    )
    assert grant.status_code == 201

    class Request:
        def __init__(self) -> None:
            self.calls = 0

        async def is_disconnected(self) -> bool:
            self.calls += 1
            return self.calls > 4

    stream = event_stream(
        Request(),  # type: ignore[arg-type]
        "events-viewer@retos.dev",
        None,
        SQLAlchemyUnitOfWork(client.app.state.session_factory),
    )
    events = [await anext(stream) for _ in range(2)]
    payloads = [event["data"] for event in events]

    assert any(granted_job.json()["id"] in payload for payload in payloads)
    assert all(hidden_job.json()["id"] not in payload for payload in payloads)


@pytest.mark.asyncio
async def test_persisted_replay_honors_viewer_progress_cursor(client: TestClient) -> None:
    login = client.post(
        "/auth/login",
        json={"email": "admin@retos.dev", "password": "test-admin-password"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    domain = client.post(
        "/domains",
        headers=headers,
        json={"slug": "events-cursor", "name": "Events Cursor"},
    )
    viewer = client.post(
        "/admin/users",
        headers=headers,
        json={
            "email": "cursor-viewer@retos.dev",
            "password": "cursor-viewer-password",
            "roles": ["viewer"],
        },
    )
    grant = client.post(
        f"/admin/users/{viewer.json()['id']}/domain-grants",
        headers=headers,
        json={"domain_id": domain.json()["id"]},
    )
    first_job = client.post(
        "/jobs",
        headers=headers,
        json={
            "kind": "index.domain",
            "domain_id": domain.json()["id"],
            "payload": {"order": 1},
        },
    )
    second_job = client.post(
        "/jobs",
        headers=headers,
        json={
            "kind": "index.domain",
            "domain_id": domain.json()["id"],
            "payload": {"order": 2},
        },
    )
    assert grant.status_code == 201

    async with SQLAlchemyUnitOfWork(client.app.state.session_factory) as uow:
        visible = await uow.progress_events.list_chronological_for_domain_ids(
            domain_ids={domain.json()["id"]},
            limit=10,
        )
    replayed = await persisted_replay_events(
        uow=SQLAlchemyUnitOfWork(client.app.state.session_factory),
        actor="cursor-viewer@retos.dev",
        last_event_id=f"progress:{visible[0].id}",
    )

    payloads = [event.model_dump_json() for event in replayed]
    assert any(second_job.json()["id"] in payload for payload in payloads)
    assert all(first_job.json()["id"] not in payload for payload in payloads)


@pytest.mark.asyncio
async def test_live_event_visibility_is_domain_scoped(client: TestClient) -> None:
    login = client.post(
        "/auth/login",
        json={"email": "admin@retos.dev", "password": "test-admin-password"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    granted_domain = client.post(
        "/domains",
        headers=headers,
        json={"slug": "live-granted", "name": "Live Granted"},
    )
    hidden_domain = client.post(
        "/domains",
        headers=headers,
        json={"slug": "live-hidden", "name": "Live Hidden"},
    )
    viewer = client.post(
        "/admin/users",
        headers=headers,
        json={
            "email": "live-viewer@retos.dev",
            "password": "live-viewer-password",
            "roles": ["viewer"],
        },
    )
    grant = client.post(
        f"/admin/users/{viewer.json()['id']}/domain-grants",
        headers=headers,
        json={"domain_id": granted_domain.json()["id"]},
    )
    granted_job = client.post(
        "/jobs",
        headers=headers,
        json={
            "kind": "index.domain",
            "domain_id": granted_domain.json()["id"],
            "payload": {"reason": "granted"},
        },
    )
    hidden_job = client.post(
        "/jobs",
        headers=headers,
        json={
            "kind": "index.domain",
            "domain_id": hidden_domain.json()["id"],
            "payload": {"reason": "hidden"},
        },
    )
    assert grant.status_code == 201
    uow = SQLAlchemyUnitOfWork(client.app.state.session_factory)

    assert await live_event_visible_to_actor(
        item=ProgressEvent(id="live:1", event="system.ready", data={}),
        actor="live-viewer@retos.dev",
        uow=uow,
    )
    assert await live_event_visible_to_actor(
        item=ProgressEvent(
            id="live:2",
            event="job.queued",
            data={"domain_id": granted_domain.json()["id"]},
        ),
        actor="live-viewer@retos.dev",
        uow=uow,
    )
    assert await live_event_visible_to_actor(
        item=ProgressEvent(
            id="live:3",
            event="job.queued",
            data={"job_id": granted_job.json()["id"]},
        ),
        actor="live-viewer@retos.dev",
        uow=uow,
    )
    assert not await live_event_visible_to_actor(
        item=ProgressEvent(
            id="live:4",
            event="job.queued",
            data={"domain_id": hidden_domain.json()["id"]},
        ),
        actor="live-viewer@retos.dev",
        uow=uow,
    )
    assert not await live_event_visible_to_actor(
        item=ProgressEvent(
            id="live:5",
            event="job.queued",
            data={"job_id": hidden_job.json()["id"]},
        ),
        actor="live-viewer@retos.dev",
        uow=uow,
    )


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
        "admin@retos.dev",
        "progress:missing-progress-event",
        SQLAlchemyUnitOfWork(client.app.state.session_factory),
    )
    event = await anext(stream)

    assert event["id"].startswith("live:")


@pytest.mark.asyncio
async def test_event_stream_skips_live_events_hidden_from_actor(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    progress_store.reset()
    progress_store.append("job.queued", {"domain_id": "hidden-domain"})
    visible = progress_store.append("job.queued", {"domain_id": "visible-domain"})

    async def fake_replay(**_: object) -> list[ProgressEvent]:
        return []

    async def fake_visibility(*, item: ProgressEvent, actor: str, uow: object) -> bool:
        return item.id == visible.id

    class Request:
        def __init__(self) -> None:
            self.calls = 0

        async def is_disconnected(self) -> bool:
            self.calls += 1
            return self.calls > 2

    monkeypatch.setattr("retos.api.routes.events.persisted_replay_events", fake_replay)
    monkeypatch.setattr("retos.api.routes.events.live_event_visible_to_actor", fake_visibility)

    stream = event_stream(
        Request(),  # type: ignore[arg-type]
        "viewer@retos.dev",
        "live:1",
        SQLAlchemyUnitOfWork(client.app.state.session_factory),
    )
    event = await anext(stream)

    assert event["id"] == visible.id


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
        scoped_empty = await uow.progress_events.list_for_domain_ids(domain_ids=set(), limit=10)
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
    assert scoped_empty == []
    assert any(event.job_id == second_job.json()["id"] for event in after_first)
    assert len(after_missing) == 2
