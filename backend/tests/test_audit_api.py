from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from retos.api.app import create_app
from retos.api.routes.audit import AuditHashChainEntryRead, validate_audit_chain
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


def create_viewer_with_grant(
    client: TestClient,
    headers: dict[str, str],
    *,
    domain_id: str,
) -> dict[str, str]:
    created = client.post(
        "/admin/users",
        headers=headers,
        json={
            "email": "audit-viewer@retos.dev",
            "password": "audit-viewer-password",
            "roles": ["viewer"],
        },
    )
    assert created.status_code == 201
    grant = client.post(
        f"/admin/users/{created.json()['id']}/domain-grants",
        headers=headers,
        json={"domain_id": domain_id},
    )
    assert grant.status_code == 201
    login = client.post(
        "/auth/login",
        json={"email": "audit-viewer@retos.dev", "password": "audit-viewer-password"},
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


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
    assert journals[0]["trace_id"] == second_job_id
    assert journals[0]["actor"] == "admin@retos.dev"
    assert journals[0]["payload"]["kind"] == "index.domain"
    assert journals[0]["occurred_at"]

    assert [event["event_type"] for event in progress_events] == [
        "job.queued",
        "job.queued",
    ]
    assert [event["job_id"] for event in progress_events] == [second_job_id, first_job_id]
    assert [event["trace_id"] for event in progress_events] == [second_job_id, first_job_id]
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
    assert body["schema_version"] == "retos.audit-export.v2"
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
    assert any(
        event["event_type"] == "job.created" and event["trace_id"] == job_id
        for event in body["journal_events"]
    )
    assert any(
        event["event_type"] == "job.queued" and event["trace_id"] == job_id
        for event in body["progress_events"]
    )
    integrity = body["integrity"]
    assert integrity["algorithm"] == "sha256"
    assert integrity["canonicalization"] == "json-sort-keys-v1"
    assert integrity["valid"] is True
    assert integrity["event_count"] == len(body["journal_events"]) + len(body["progress_events"])
    assert integrity["head_hash"] == integrity["chain"][-1]["event_hash"]
    assert integrity["chain"][0]["prev_hash"] is None
    assert all(entry["payload_hash"] for entry in integrity["chain"])
    assert all(entry["event_hash"] for entry in integrity["chain"])
    assert {entry["event_stream"] for entry in integrity["chain"]} == {"journal", "progress"}
    assert any(entry["trace_id"] == job_id for entry in integrity["chain"])
    assert any(entry["event_type"] == "job.created" for entry in integrity["chain"])
    assert any(entry["event_type"] == "job.queued" for entry in integrity["chain"])
    assert [
        (entry["occurred_at"], entry["event_stream"], entry["event_id"])
        for entry in integrity["chain"]
    ] == sorted(
        (entry["occurred_at"], entry["event_stream"], entry["event_id"])
        for entry in integrity["chain"]
    )


def test_audit_hash_chain_validation_detects_tampering(
    audit_client: TestClient,
    audit_admin_headers: dict[str, str],
) -> None:
    domain_id = create_domain(audit_client, audit_admin_headers, "audit-chain")
    create_index_job(audit_client, audit_admin_headers, domain_id)
    response = audit_client.get(
        "/audit/export?limit=5",
        headers=audit_admin_headers,
    )
    assert response.status_code == 200
    entries = [
        AuditHashChainEntryRead.model_validate(entry)
        for entry in response.json()["integrity"]["chain"]
    ]
    assert validate_audit_chain(entries) is True

    tampered = [
        entry.model_copy(update={"payload_hash": "0" * 64}) if index == 0 else entry
        for index, entry in enumerate(entries)
    ]

    assert validate_audit_chain(tampered) is False


def test_viewer_audit_is_scoped_to_granted_domains(
    audit_client: TestClient,
    audit_admin_headers: dict[str, str],
) -> None:
    granted_domain_id = create_domain(audit_client, audit_admin_headers, "audit-granted")
    hidden_domain_id = create_domain(audit_client, audit_admin_headers, "audit-hidden")
    granted_job_id = create_index_job(audit_client, audit_admin_headers, granted_domain_id)
    hidden_job_id = create_index_job(audit_client, audit_admin_headers, hidden_domain_id)
    viewer_headers = create_viewer_with_grant(
        audit_client,
        audit_admin_headers,
        domain_id=granted_domain_id,
    )

    journal_response = audit_client.get("/audit/journal-events?limit=20", headers=viewer_headers)
    progress_response = audit_client.get("/audit/progress-events?limit=20", headers=viewer_headers)
    export_response = audit_client.get("/audit/export?limit=20", headers=viewer_headers)

    assert journal_response.status_code == 200
    assert progress_response.status_code == 200
    assert export_response.status_code == 200
    assert any(event["entity_id"] == granted_job_id for event in journal_response.json())
    assert all(event["entity_id"] != hidden_job_id for event in journal_response.json())
    assert any(event["job_id"] == granted_job_id for event in progress_response.json())
    assert all(event["job_id"] != hidden_job_id for event in progress_response.json())
    exported = export_response.json()
    assert any(event["entity_id"] == granted_job_id for event in exported["journal_events"])
    assert all(event["entity_id"] != hidden_job_id for event in exported["journal_events"])


def test_audit_export_limit_is_validated(
    audit_client: TestClient,
    audit_admin_headers: dict[str, str],
) -> None:
    response = audit_client.get(
        "/audit/export?limit=1001",
        headers=audit_admin_headers,
    )

    assert response.status_code == 422
