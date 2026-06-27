from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from retos.api.app import create_app
from retos.core.config import Settings


@pytest.fixture
def audit_client(settings: Settings, tmp_path: Path) -> Iterator[TestClient]:
    local_settings = settings.model_copy(
        update={
            "database_url": f"sqlite+aiosqlite:///{tmp_path / 'retos-audit.db'}",
            "database_create_all": True,
        }
    )
    with TestClient(create_app(local_settings)) as test_client:
        yield test_client


@pytest.fixture
def audit_admin_headers(audit_client: TestClient) -> dict[str, str]:
    response = audit_client.post(
        "/auth/login",
        json={"email": "admin@retos.dev", "password": "test-admin-password"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def create_domain(client: TestClient, headers: dict[str, str], slug: str) -> str:
    response = client.post(
        "/domains",
        json={"slug": slug, "name": "Audit Domain"},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()["id"]


def create_index_job(client: TestClient, headers: dict[str, str], domain_id: str) -> str:
    response = client.post(
        "/jobs",
        json={
            "kind": "index.domain",
            "domain_id": domain_id,
            "payload": {"reason": "audit-test"},
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()["id"]


@pytest.mark.parametrize(
    "path",
    ["/audit/journal-events", "/audit/progress-events", "/audit/export"],
)
def test_audit_events_require_admin_token(audit_client: TestClient, path: str) -> None:
    response = audit_client.get(path)

    assert response.status_code == 401


def test_lists_persisted_journal_and_progress_events(
    audit_client: TestClient,
    audit_admin_headers: dict[str, str],
) -> None:
    first_domain_id = create_domain(audit_client, audit_admin_headers, "audit-first")
    second_domain_id = create_domain(audit_client, audit_admin_headers, "audit-second")
    first_job_id = create_index_job(audit_client, audit_admin_headers, first_domain_id)
    second_job_id = create_index_job(audit_client, audit_admin_headers, second_domain_id)

    journal_response = audit_client.get(
        "/audit/journal-events?limit=1",
        headers=audit_admin_headers,
    )
    progress_response = audit_client.get(
        "/audit/progress-events?limit=2",
        headers=audit_admin_headers,
    )

    assert journal_response.status_code == 200
    assert progress_response.status_code == 200

    journals = journal_response.json()
    progress_events = progress_response.json()
    assert len(journals) == 1
    assert journals[0]["event_type"] == "job.created"
    assert journals[0]["entity_type"] == "job"
    assert journals[0]["entity_id"] == second_job_id
    assert journals[0]["actor"] == "admin@retos.dev"
    assert journals[0]["payload"]["kind"] == "index.domain"
    assert journals[0]["occurred_at"]

    assert [event["event_type"] for event in progress_events] == [
        "job.queued",
        "job.queued",
    ]
    assert [event["job_id"] for event in progress_events] == [second_job_id, first_job_id]
    assert progress_events[0]["message"] == "Queued index.domain"
    assert progress_events[0]["payload"] == {"status": "queued"}
    assert progress_events[0]["occurred_at"]


def test_audit_event_limit_is_validated(
    audit_client: TestClient,
    audit_admin_headers: dict[str, str],
) -> None:
    response = audit_client.get(
        "/audit/journal-events?limit=0",
        headers=audit_admin_headers,
    )

    assert response.status_code == 422


def test_exports_audit_snapshot_with_download_headers(
    audit_client: TestClient,
    audit_admin_headers: dict[str, str],
) -> None:
    domain_id = create_domain(audit_client, audit_admin_headers, "audit-export")
    job_id = create_index_job(audit_client, audit_admin_headers, domain_id)

    response = audit_client.get(
        "/audit/export?limit=5",
        headers=audit_admin_headers,
    )

    assert response.status_code == 200
    assert response.headers["content-disposition"] == (
        'attachment; filename="retos-audit-export.json"'
    )
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["schema_version"] == "retos.audit-export.v1"
    assert body["generated_at"]
    assert body["limit"] == 5
    assert any(
        event["event_type"] == "job.created" and event["entity_id"] == job_id
        for event in body["journal_events"]
    )
    assert any(
        event["event_type"] == "job.queued" and event["job_id"] == job_id
        for event in body["progress_events"]
    )


def test_audit_export_limit_is_validated(
    audit_client: TestClient,
    audit_admin_headers: dict[str, str],
) -> None:
    response = audit_client.get(
        "/audit/export?limit=1001",
        headers=audit_admin_headers,
    )

    assert response.status_code == 422
