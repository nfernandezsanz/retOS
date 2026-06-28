import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from retos.api.app import create_app
from retos.api.routes.ingestions import enqueue_text_ingestion
from retos.core.config import Settings
from retos.domain.documents import utc_now
from retos.domain.jobs import Job
from retos.ingestion.text import (
    TextIngestionError,
    chunk_text,
    content_hash,
    fail_text_ingestion_job,
    run_text_ingestion,
)
from retos.persistence.unit_of_work import SQLAlchemyUnitOfWork


@pytest.fixture
def ingestion_db_path(tmp_path: Path) -> Path:
    return tmp_path / "retos-ingestion.db"


@pytest.fixture
def ingestion_client(settings: Settings, ingestion_db_path: Path) -> Iterator[TestClient]:
    local_settings = settings.model_copy(
        update={
            "database_url": f"sqlite+aiosqlite:///{ingestion_db_path}",
            "database_create_all": True,
        }
    )
    with TestClient(create_app(local_settings)) as test_client:
        yield test_client


@pytest.fixture
def ingestion_admin_headers(ingestion_client: TestClient) -> dict[str, str]:
    response = ingestion_client.post(
        "/auth/login",
        json={"email": "admin@retos.dev", "password": "test-admin-password"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def create_domain_and_source(
    client: TestClient,
    headers: dict[str, str],
) -> tuple[str, str]:
    domain_response = client.post(
        "/domains",
        json={"slug": "ingestion-domain", "name": "Ingestion Domain"},
        headers=headers,
    )
    domain_id = domain_response.json()["id"]
    source_response = client.post(
        f"/domains/{domain_id}/sources",
        json={"kind": "upload", "name": "Inline corpus", "uri": "inline://corpus"},
        headers=headers,
    )
    return domain_id, source_response.json()["id"]


def count_ingestion_side_effects(db_path: Path) -> tuple[int, int, int, int, int]:
    connection = sqlite3.connect(db_path)
    try:
        documents = connection.execute("select count(*) from documents").fetchone()[0]
        artifacts = connection.execute("select count(*) from artifacts").fetchone()[0]
        segments = connection.execute("select count(*) from segments").fetchone()[0]
        journals = connection.execute("select count(*) from journal_events").fetchone()[0]
        progress = connection.execute("select count(*) from progress_events").fetchone()[0]
        return int(documents), int(artifacts), int(segments), int(journals), int(progress)
    finally:
        connection.close()


async def add_text_job(
    client: TestClient,
    *,
    kind: str = "ingest.source",
    status: str = "queued",
    domain_id: str | None = None,
    source_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> str:
    async with SQLAlchemyUnitOfWork(client.app.state.session_factory) as uow:
        job = await uow.jobs.add(
            kind=kind,  # type: ignore[arg-type]
            status=status,  # type: ignore[arg-type]
            domain_id=domain_id,
            source_id=source_id,
            payload=(
                payload if payload is not None else {"title": "Fixture", "text": "fixture text"}
            ),
        )
        await uow.commit()
    return job.id


def test_chunk_text_is_deterministic() -> None:
    drafts = chunk_text("alpha beta gamma delta epsilon", max_tokens=2)

    assert [draft.text for draft in drafts] == ["alpha beta", "gamma delta", "epsilon"]
    assert [draft.anchor for draft in drafts] == ["word=0", "word=2", "word=4"]
    assert drafts[0].content_hash == content_hash("alpha beta")


def test_chunk_text_rejects_invalid_input() -> None:
    with pytest.raises(TextIngestionError, match="non-empty text"):
        chunk_text("   ")

    with pytest.raises(ValueError, match="positive"):
        chunk_text("alpha", max_tokens=0)


def test_enqueue_text_ingestion_dispatches_celery_task(monkeypatch: pytest.MonkeyPatch) -> None:
    delayed: list[str] = []
    now = utc_now()
    job = Job(
        id="job-123",
        kind="ingest.source",
        status="queued",
        domain_id="domain-123",
        source_id=None,
        payload={},
        error=None,
        started_at=None,
        completed_at=None,
        created_at=now,
        updated_at=now,
    )

    monkeypatch.setattr(
        "retos.api.routes.ingestions.ingest_text_job.delay",
        lambda job_id: delayed.append(job_id),
    )

    enqueue_text_ingestion(job)

    assert delayed == ["job-123"]


def test_text_ingestion_endpoint_queues_job_without_broker_in_test_env(
    ingestion_client: TestClient,
    ingestion_admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enqueued: list[str] = []
    domain_id, source_id = create_domain_and_source(ingestion_client, ingestion_admin_headers)

    def fake_enqueue(job: Job) -> None:
        enqueued.append(job.id)

    monkeypatch.setattr("retos.api.routes.ingestions.enqueue_text_ingestion", fake_enqueue)

    response = ingestion_client.post(
        f"/domains/{domain_id}/ingestions/text",
        headers=ingestion_admin_headers,
        json={
            "source_id": source_id,
            "title": "Inline fixture",
            "text": "A small corpus that should be processed by the worker.",
            "metadata": {"fixture": True},
            "max_segment_tokens": 20,
        },
    )

    assert response.status_code == 202
    job = response.json()
    assert job["kind"] == "ingest.source"
    assert job["status"] == "queued"
    assert job["domain_id"] == domain_id
    assert job["source_id"] == source_id
    assert enqueued == []


@pytest.mark.asyncio
async def test_run_text_ingestion_persists_document_artifact_segments_and_events(
    ingestion_client: TestClient,
    ingestion_admin_headers: dict[str, str],
    ingestion_db_path: Path,
) -> None:
    domain_id, source_id = create_domain_and_source(ingestion_client, ingestion_admin_headers)
    text = " ".join(f"token-{index}" for index in range(45))
    created_job = ingestion_client.post(
        "/jobs",
        headers=ingestion_admin_headers,
        json={
            "kind": "ingest.source",
            "domain_id": domain_id,
            "source_id": source_id,
            "payload": {
                "title": "Service fixture",
                "text": text,
                "source_uri": "inline://corpus/service-fixture.txt",
                "metadata": {"language": "en"},
                "max_segment_tokens": 20,
            },
        },
    )
    job_id = created_job.json()["id"]
    session_factory = ingestion_client.app.state.session_factory

    result = await run_text_ingestion(
        job_id=job_id,
        uow=SQLAlchemyUnitOfWork(session_factory),
        actor="test-suite",
    )

    assert result.document.title == "Service fixture"
    assert result.document.content_hash == content_hash(text)
    assert result.version.size_bytes == len(text.encode("utf-8"))
    assert len(result.segments) == 3
    assert [segment.ordinal for segment in result.segments] == [0, 1, 2]

    fetched_job = ingestion_client.get(f"/jobs/{job_id}", headers=ingestion_admin_headers)
    assert fetched_job.status_code == 200
    assert fetched_job.json()["status"] == "succeeded"

    artifacts = ingestion_client.get(
        f"/document-versions/{result.version.id}/artifacts",
        headers=ingestion_admin_headers,
    )
    assert artifacts.status_code == 200
    assert artifacts.json()[0]["kind"] == "raw_text"

    assert count_ingestion_side_effects(ingestion_db_path) == (1, 1, 3, 4, 3)


@pytest.mark.asyncio
async def test_fail_text_ingestion_job_marks_job_failed(
    ingestion_client: TestClient,
    ingestion_admin_headers: dict[str, str],
    ingestion_db_path: Path,
) -> None:
    domain_id, source_id = create_domain_and_source(ingestion_client, ingestion_admin_headers)
    created_job = ingestion_client.post(
        "/jobs",
        headers=ingestion_admin_headers,
        json={
            "kind": "ingest.source",
            "domain_id": domain_id,
            "source_id": source_id,
            "payload": {"title": "Broken", "text": "broken"},
        },
    )
    job_id = created_job.json()["id"]

    await fail_text_ingestion_job(
        job_id=job_id,
        uow=SQLAlchemyUnitOfWork(ingestion_client.app.state.session_factory),
        error="boom",
        actor="test-suite",
    )

    fetched_job = ingestion_client.get(f"/jobs/{job_id}", headers=ingestion_admin_headers)
    assert fetched_job.status_code == 200
    assert fetched_job.json()["status"] == "failed"
    assert fetched_job.json()["error"] == "boom"
    assert count_ingestion_side_effects(ingestion_db_path) == (0, 0, 0, 2, 2)


@pytest.mark.asyncio
async def test_fail_text_ingestion_job_ignores_missing_job(
    ingestion_client: TestClient,
    ingestion_db_path: Path,
) -> None:
    await fail_text_ingestion_job(
        job_id="missing-job",
        uow=SQLAlchemyUnitOfWork(ingestion_client.app.state.session_factory),
        error="boom",
    )

    assert count_ingestion_side_effects(ingestion_db_path) == (0, 0, 0, 0, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("job_kwargs", "message"),
    [
        ({"kind": "index.domain"}, "Unsupported ingestion job kind"),
        ({"status": "running"}, "Job must be queued"),
        ({"domain_id": None}, "requires a domain_id"),
        ({"payload": {"title": "Bad", "text": "body", "metadata": "not-object"}}, "metadata"),
        ({"payload": {"title": "Bad", "text": "body", "external_id": 123}}, "external_id"),
        ({"payload": {"title": "Bad", "text": "body", "max_segment_tokens": -1}}, "positive"),
    ],
)
async def test_run_text_ingestion_rejects_invalid_job_payloads(
    ingestion_client: TestClient,
    ingestion_admin_headers: dict[str, str],
    ingestion_db_path: Path,
    job_kwargs: dict[str, Any],
    message: str,
) -> None:
    domain_id, _ = create_domain_and_source(ingestion_client, ingestion_admin_headers)
    job_kwargs.setdefault("domain_id", domain_id)
    job_id = await add_text_job(ingestion_client, **job_kwargs)

    with pytest.raises((TextIngestionError, ValueError), match=message):
        await run_text_ingestion(
            job_id=job_id,
            uow=SQLAlchemyUnitOfWork(ingestion_client.app.state.session_factory),
        )

    assert count_ingestion_side_effects(ingestion_db_path) == (0, 0, 0, 0, 0)


@pytest.mark.asyncio
async def test_run_text_ingestion_rejects_missing_source(
    ingestion_client: TestClient,
    ingestion_admin_headers: dict[str, str],
) -> None:
    domain_id, _ = create_domain_and_source(ingestion_client, ingestion_admin_headers)
    job_id = await add_text_job(
        ingestion_client,
        domain_id=domain_id,
        source_id="missing-source",
    )

    with pytest.raises(TextIngestionError, match="Source not found"):
        await run_text_ingestion(
            job_id=job_id,
            uow=SQLAlchemyUnitOfWork(ingestion_client.app.state.session_factory),
        )


@pytest.mark.asyncio
async def test_run_text_ingestion_rejects_duplicate_content(
    ingestion_client: TestClient,
    ingestion_admin_headers: dict[str, str],
) -> None:
    domain_id, _ = create_domain_and_source(ingestion_client, ingestion_admin_headers)
    text = "Duplicate inline content"
    ingestion_client.post(
        f"/domains/{domain_id}/documents",
        headers=ingestion_admin_headers,
        json={
            "external_id": "existing",
            "title": "Existing",
            "content_hash": content_hash(text),
            "source_uri": "inline://existing",
            "size_bytes": len(text.encode("utf-8")),
        },
    )
    job_id = await add_text_job(
        ingestion_client,
        domain_id=domain_id,
        payload={"title": "Duplicate", "text": text},
    )

    with pytest.raises(TextIngestionError, match="already exists"):
        await run_text_ingestion(
            job_id=job_id,
            uow=SQLAlchemyUnitOfWork(ingestion_client.app.state.session_factory),
        )


def test_text_ingestion_rejects_source_from_another_domain(
    ingestion_client: TestClient,
    ingestion_admin_headers: dict[str, str],
) -> None:
    domain_id, _ = create_domain_and_source(ingestion_client, ingestion_admin_headers)
    second_domain = ingestion_client.post(
        "/domains",
        json={"slug": "ingestion-other", "name": "Other"},
        headers=ingestion_admin_headers,
    )
    other_id = second_domain.json()["id"]
    source = ingestion_client.post(
        f"/domains/{other_id}/sources",
        json={"kind": "upload", "name": "Other source", "uri": "inline://other"},
        headers=ingestion_admin_headers,
    )

    response = ingestion_client.post(
        f"/domains/{domain_id}/ingestions/text",
        headers=ingestion_admin_headers,
        json={
            "source_id": source.json()["id"],
            "title": "Wrong source",
            "text": "This should not be queued.",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Source does not belong to domain"


def test_text_ingestion_rejects_missing_domain(
    ingestion_client: TestClient,
    ingestion_admin_headers: dict[str, str],
) -> None:
    response = ingestion_client.post(
        "/domains/missing/ingestions/text",
        headers=ingestion_admin_headers,
        json={"title": "Missing", "text": "No domain."},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Domain not found"
