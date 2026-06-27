import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from retos.api.app import create_app
from retos.core.config import Settings


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
