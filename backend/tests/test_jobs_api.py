import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from retos.api.app import create_app
from retos.api.routes.jobs import (
    RetryDispatchPlan,
    dispatch_retry_job,
    retry_dispatch_plan,
)
from retos.core.config import Settings
from retos.domain.jobs import Job


@pytest.fixture
def jobs_db_path(tmp_path: Path) -> Path:
    return tmp_path / "retos-jobs.db"


@pytest.fixture
def jobs_client(settings: Settings, jobs_db_path: Path) -> Iterator[TestClient]:
    local_settings = settings.model_copy(
        update={
            "database_url": f"sqlite+aiosqlite:///{jobs_db_path}",
            "database_create_all": True,
        }
    )
    with TestClient(create_app(local_settings)) as test_client:
        yield test_client


@pytest.fixture
def jobs_admin_headers(jobs_client: TestClient) -> dict[str, str]:
    response = jobs_client.post(
        "/auth/login",
        json={"email": "admin@retos.dev", "password": "test-admin-password"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def create_domain_and_source(
    client: TestClient,
    headers: dict[str, str],
    *,
    slug: str = "jobs-domain",
) -> tuple[str, str]:
    domain_response = client.post(
        "/domains",
        json={"slug": slug, "name": "Jobs Domain"},
        headers=headers,
    )
    domain_id = domain_response.json()["id"]
    source_response = client.post(
        f"/domains/{domain_id}/sources",
        json={"kind": "mount", "name": "Jobs Source", "uri": f"file:///tmp/{slug}"},
        headers=headers,
    )
    return domain_id, source_response.json()["id"]


def count_audit_rows(db_path: Path) -> tuple[int, int]:
    connection = sqlite3.connect(db_path)
    try:
        journal_cursor = connection.execute("select count(*) from journal_events")
        progress_cursor = connection.execute("select count(*) from progress_events")
        return int(journal_cursor.fetchone()[0]), int(progress_cursor.fetchone()[0])
    finally:
        connection.close()


def create_job(
    client: TestClient,
    headers: dict[str, str],
    *,
    kind: str = "ingest.source",
) -> dict[str, object]:
    domain_id, source_id = create_domain_and_source(client, headers)
    response = client.post(
        "/jobs",
        json={
            "kind": kind,
            "domain_id": domain_id,
            "source_id": source_id,
            "payload": {"reason": "api-test"},
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def job_fixture(
    *,
    kind: str,
    domain_id: str | None = "domain-1",
    source_id: str | None = None,
    payload: dict[str, object] | None = None,
) -> Job:
    now = datetime.now(UTC)
    return Job(
        id="job-fixture",
        kind=kind,  # type: ignore[arg-type]
        status="failed",
        domain_id=domain_id,
        source_id=source_id,
        payload=payload or {},
        error="fixture failure",
        started_at=now,
        completed_at=now,
        created_at=now,
        updated_at=now,
    )


def test_jobs_require_admin_token(jobs_client: TestClient) -> None:
    response = jobs_client.get("/jobs")

    assert response.status_code == 401


def test_create_list_and_get_job(
    jobs_client: TestClient,
    jobs_admin_headers: dict[str, str],
    jobs_db_path: Path,
) -> None:
    domain_id, source_id = create_domain_and_source(jobs_client, jobs_admin_headers)

    created = jobs_client.post(
        "/jobs",
        json={
            "kind": "ingest.source",
            "domain_id": domain_id,
            "source_id": source_id,
            "payload": {"reason": "api-test"},
        },
        headers=jobs_admin_headers,
    )

    assert created.status_code == 201
    job = created.json()
    assert job["kind"] == "ingest.source"
    assert job["status"] == "queued"
    assert job["domain_id"] == domain_id
    assert job["source_id"] == source_id
    assert job["payload"] == {"reason": "api-test"}
    assert job["created_at"]
    assert job["updated_at"]

    listed = jobs_client.get("/jobs", headers=jobs_admin_headers)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [job["id"]]

    fetched = jobs_client.get(f"/jobs/{job['id']}", headers=jobs_admin_headers)
    assert fetched.status_code == 200
    assert fetched.json()["id"] == job["id"]

    assert count_audit_rows(jobs_db_path) == (1, 1)


def test_job_transition_lifecycle(
    jobs_client: TestClient,
    jobs_admin_headers: dict[str, str],
    jobs_db_path: Path,
) -> None:
    job = create_job(jobs_client, jobs_admin_headers)

    started = jobs_client.post(f"/jobs/{job['id']}/start", headers=jobs_admin_headers)
    assert started.status_code == 200
    assert started.json()["status"] == "running"
    assert started.json()["started_at"]
    assert started.json()["completed_at"] is None

    completed = jobs_client.post(f"/jobs/{job['id']}/complete", headers=jobs_admin_headers)
    assert completed.status_code == 200
    assert completed.json()["status"] == "succeeded"
    assert completed.json()["completed_at"]

    assert count_audit_rows(jobs_db_path) == (3, 3)


def test_job_failure_records_error(
    jobs_client: TestClient,
    jobs_admin_headers: dict[str, str],
) -> None:
    job = create_job(jobs_client, jobs_admin_headers, kind="index.domain")

    started = jobs_client.post(f"/jobs/{job['id']}/start", headers=jobs_admin_headers)
    failed = jobs_client.post(
        f"/jobs/{job['id']}/fail",
        json={"error": "fixture failure"},
        headers=jobs_admin_headers,
    )

    assert started.status_code == 200
    assert failed.status_code == 200
    assert failed.json()["status"] == "failed"
    assert failed.json()["error"] == "fixture failure"


def test_job_transition_rejects_invalid_order(
    jobs_client: TestClient,
    jobs_admin_headers: dict[str, str],
) -> None:
    job = create_job(jobs_client, jobs_admin_headers)

    response = jobs_client.post(f"/jobs/{job['id']}/complete", headers=jobs_admin_headers)

    assert response.status_code == 409
    assert response.json()["detail"] == "Cannot transition job from queued to succeeded"


def test_cancel_job_from_queue(
    jobs_client: TestClient,
    jobs_admin_headers: dict[str, str],
) -> None:
    job = create_job(jobs_client, jobs_admin_headers)

    response = jobs_client.post(f"/jobs/{job['id']}/cancel", headers=jobs_admin_headers)

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert response.json()["completed_at"]


def test_retry_failed_index_job_creates_audited_queued_job(
    jobs_client: TestClient,
    jobs_admin_headers: dict[str, str],
    jobs_db_path: Path,
) -> None:
    domain_id, _ = create_domain_and_source(jobs_client, jobs_admin_headers)
    created = jobs_client.post(
        "/jobs",
        json={
            "kind": "index.domain",
            "domain_id": domain_id,
            "payload": {"requested_at": "fixture"},
        },
        headers=jobs_admin_headers,
    )
    assert created.status_code == 201
    original = created.json()
    assert (
        jobs_client.post(f"/jobs/{original['id']}/start", headers=jobs_admin_headers).status_code
        == 200
    )
    failed = jobs_client.post(
        f"/jobs/{original['id']}/fail",
        json={"error": "fixture failure"},
        headers=jobs_admin_headers,
    )
    assert failed.status_code == 200

    retried = jobs_client.post(f"/jobs/{original['id']}/retry", headers=jobs_admin_headers)

    assert retried.status_code == 202
    retry_job = retried.json()
    assert retry_job["id"] != original["id"]
    assert retry_job["kind"] == "index.domain"
    assert retry_job["status"] == "queued"
    assert retry_job["domain_id"] == domain_id
    assert retry_job["payload"]["requested_at"] == "fixture"
    assert retry_job["payload"]["retried_from_job_id"] == original["id"]
    assert retry_job["payload"]["retry_requested_at"]

    listed = jobs_client.get("/jobs", headers=jobs_admin_headers)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()[:2]] == [retry_job["id"], original["id"]]

    connection = sqlite3.connect(jobs_db_path)
    try:
        journal_count = connection.execute(
            "select count(*) from journal_events where event_type = 'job.retry_queued'"
        ).fetchone()[0]
        progress_count = connection.execute(
            "select count(*) from progress_events where event_type = 'job.retry_queued'"
        ).fetchone()[0]
    finally:
        connection.close()
    assert (journal_count, progress_count) == (1, 1)


def test_retry_rejects_active_or_unsupported_jobs(
    jobs_client: TestClient,
    jobs_admin_headers: dict[str, str],
) -> None:
    queued = create_job(jobs_client, jobs_admin_headers)

    active_retry = jobs_client.post(f"/jobs/{queued['id']}/retry", headers=jobs_admin_headers)

    assert active_retry.status_code == 409
    assert active_retry.json()["detail"] == "Cannot retry job from queued"

    started = jobs_client.post(f"/jobs/{queued['id']}/start", headers=jobs_admin_headers)
    assert started.status_code == 200
    failed = jobs_client.post(
        f"/jobs/{queued['id']}/fail",
        json={"error": "manual job has no worker payload"},
        headers=jobs_admin_headers,
    )
    assert failed.status_code == 200

    unsupported_retry = jobs_client.post(f"/jobs/{queued['id']}/retry", headers=jobs_admin_headers)

    assert unsupported_retry.status_code == 422
    assert "cannot be retried" in unsupported_retry.json()["detail"]


@pytest.mark.parametrize(
    ("job", "task_name"),
    [
        (job_fixture(kind="index.domain"), "rebuild_domain_index"),
        (
            job_fixture(kind="agent.query", payload={"question": "What happened?"}),
            "agent_query",
        ),
        (
            job_fixture(
                kind="ingest.source",
                payload={"ingestion_kind": "file_upload", "file_path": "/var/lib/retos/file.txt"},
            ),
            "ingest_file_upload",
        ),
        (
            job_fixture(
                kind="ingest.source",
                source_id="source-1",
                payload={"ingestion_kind": "source_scan"},
            ),
            "scan_source",
        ),
        (
            job_fixture(kind="ingest.source", payload={"title": "Note", "text": "Body"}),
            "ingest_text",
        ),
    ],
)
def test_retry_dispatch_plan_supports_worker_backed_jobs(
    job: Job,
    task_name: str,
) -> None:
    assert retry_dispatch_plan(job).task_name == task_name


@pytest.mark.parametrize(
    ("job", "detail"),
    [
        (job_fixture(kind="index.domain", domain_id=None), "Index retry requires domain_id"),
        (
            job_fixture(kind="agent.query", payload={}),
            "Agent query retry requires domain_id and question",
        ),
        (
            job_fixture(kind="ingest.source", payload={"ingestion_kind": "file_upload"}),
            "File upload retry requires file_path",
        ),
        (
            job_fixture(kind="ingest.source", payload={"ingestion_kind": "source_scan"}),
            "Source scan retry requires domain_id and source_id",
        ),
        (
            job_fixture(
                kind="ingest.source", domain_id=None, payload={"title": "Note", "text": "Body"}
            ),
            "Text ingestion retry requires domain_id",
        ),
        (job_fixture(kind="eval.run"), "cannot be retried"),
    ],
)
def test_retry_dispatch_plan_rejects_unrunnable_jobs(job: Job, detail: str) -> None:
    with pytest.raises(Exception) as exc_info:
        retry_dispatch_plan(job)

    assert detail in str(exc_info.value)


def test_dispatch_retry_job_calls_matching_celery_task(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []

    class FakeTask:
        def __init__(self, name: str) -> None:
            self.name = name

        def delay(self, job_id: str) -> None:
            calls.append((self.name, job_id))

    monkeypatch.setattr("retos.api.routes.jobs.rebuild_domain_index_job", FakeTask("index"))
    monkeypatch.setattr("retos.api.routes.jobs.agent_query_job", FakeTask("agent"))
    monkeypatch.setattr("retos.api.routes.jobs.ingest_file_upload_job", FakeTask("upload"))
    monkeypatch.setattr("retos.api.routes.jobs.scan_source_job", FakeTask("scan"))
    monkeypatch.setattr("retos.api.routes.jobs.ingest_text_job", FakeTask("text"))

    job = job_fixture(kind="index.domain")
    for task_name in (
        "rebuild_domain_index",
        "agent_query",
        "ingest_file_upload",
        "scan_source",
        "ingest_text",
    ):
        dispatch_retry_job(job, RetryDispatchPlan(task_name=task_name))

    assert calls == [
        ("index", "job-fixture"),
        ("agent", "job-fixture"),
        ("upload", "job-fixture"),
        ("scan", "job-fixture"),
        ("text", "job-fixture"),
    ]
    with pytest.raises(RuntimeError, match="Unsupported retry dispatch task"):
        dispatch_retry_job(job, RetryDispatchPlan(task_name="unknown"))


def test_create_job_rejects_missing_domain(
    jobs_client: TestClient,
    jobs_admin_headers: dict[str, str],
) -> None:
    response = jobs_client.post(
        "/jobs",
        json={"kind": "index.domain", "domain_id": "missing"},
        headers=jobs_admin_headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Domain not found"


def test_create_job_rejects_source_from_another_domain(
    jobs_client: TestClient,
    jobs_admin_headers: dict[str, str],
) -> None:
    domain_id, _ = create_domain_and_source(
        jobs_client,
        jobs_admin_headers,
        slug="first-domain",
    )
    _, source_id = create_domain_and_source(
        jobs_client,
        jobs_admin_headers,
        slug="second-domain",
    )

    response = jobs_client.post(
        "/jobs",
        json={
            "kind": "ingest.source",
            "domain_id": domain_id,
            "source_id": source_id,
        },
        headers=jobs_admin_headers,
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Source does not belong to domain"
