import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from retos.api.app import create_app
from retos.core.config import Settings


@pytest.fixture
def documents_db_path(tmp_path: Path) -> Path:
    return tmp_path / "retos-documents.db"


@pytest.fixture
def documents_client(settings: Settings, documents_db_path: Path) -> Iterator[TestClient]:
    local_settings = settings.model_copy(
        update={
            "database_url": f"sqlite+aiosqlite:///{documents_db_path}",
            "database_create_all": True,
        }
    )
    with TestClient(create_app(local_settings)) as test_client:
        yield test_client


@pytest.fixture
def documents_admin_headers(documents_client: TestClient) -> dict[str, str]:
    response = documents_client.post(
        "/auth/login",
        json={"email": "admin@retos.dev", "password": "test-admin-password"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def create_domain_and_source(
    client: TestClient,
    headers: dict[str, str],
    *,
    slug: str = "documents-domain",
) -> tuple[str, str]:
    domain_response = client.post(
        "/domains",
        json={"slug": slug, "name": "Documents Domain"},
        headers=headers,
    )
    domain_id = domain_response.json()["id"]
    source_response = client.post(
        f"/domains/{domain_id}/sources",
        json={"kind": "upload", "name": "Documents Source", "uri": f"upload://{slug}"},
        headers=headers,
    )
    return domain_id, source_response.json()["id"]


def count_document_side_effects(db_path: Path) -> tuple[int, int, int]:
    connection = sqlite3.connect(db_path)
    try:
        versions = connection.execute("select count(*) from document_versions").fetchone()[0]
        journals = connection.execute("select count(*) from journal_events").fetchone()[0]
        progress = connection.execute("select count(*) from progress_events").fetchone()[0]
        return int(versions), int(journals), int(progress)
    finally:
        connection.close()


def test_documents_require_admin_token(documents_client: TestClient) -> None:
    response = documents_client.get("/domains/some-domain/documents")

    assert response.status_code == 401


def test_create_list_get_and_list_document_versions(
    documents_client: TestClient,
    documents_admin_headers: dict[str, str],
    documents_db_path: Path,
) -> None:
    domain_id, source_id = create_domain_and_source(documents_client, documents_admin_headers)

    created = documents_client.post(
        f"/domains/{domain_id}/documents",
        json={
            "source_id": source_id,
            "external_id": "fixture-001",
            "title": "Fixture Document",
            "content_hash": "sha256:abc12345",
            "source_uri": "upload://documents-domain/fixture.txt",
            "size_bytes": 128,
            "metadata": {"language": "en"},
        },
        headers=documents_admin_headers,
    )

    assert created.status_code == 201
    document = created.json()
    assert document["domain_id"] == domain_id
    assert document["source_id"] == source_id
    assert document["external_id"] == "fixture-001"
    assert document["title"] == "Fixture Document"
    assert document["content_hash"] == "sha256:abc12345"
    assert document["metadata"] == {"language": "en"}

    listed = documents_client.get(
        f"/domains/{domain_id}/documents",
        headers=documents_admin_headers,
    )
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [document["id"]]

    fetched = documents_client.get(
        f"/documents/{document['id']}",
        headers=documents_admin_headers,
    )
    assert fetched.status_code == 200
    assert fetched.json()["id"] == document["id"]

    versions = documents_client.get(
        f"/documents/{document['id']}/versions",
        headers=documents_admin_headers,
    )
    assert versions.status_code == 200
    assert versions.json()[0]["version"] == 1
    assert versions.json()[0]["size_bytes"] == 128

    assert count_document_side_effects(documents_db_path) == (1, 1, 1)


def test_create_document_rejects_duplicate_hash_within_domain(
    documents_client: TestClient,
    documents_admin_headers: dict[str, str],
) -> None:
    domain_id, source_id = create_domain_and_source(documents_client, documents_admin_headers)
    payload = {
        "source_id": source_id,
        "title": "Duplicate",
        "content_hash": "sha256:dddddddd",
        "source_uri": "upload://duplicate",
        "size_bytes": 1,
    }

    first = documents_client.post(
        f"/domains/{domain_id}/documents",
        json=payload,
        headers=documents_admin_headers,
    )
    second = documents_client.post(
        f"/domains/{domain_id}/documents",
        json=payload,
        headers=documents_admin_headers,
    )

    assert first.status_code == 201
    assert second.status_code == 409


def test_create_document_rejects_source_from_another_domain(
    documents_client: TestClient,
    documents_admin_headers: dict[str, str],
) -> None:
    domain_id, _ = create_domain_and_source(
        documents_client,
        documents_admin_headers,
        slug="documents-first",
    )
    _, source_id = create_domain_and_source(
        documents_client,
        documents_admin_headers,
        slug="documents-second",
    )

    response = documents_client.post(
        f"/domains/{domain_id}/documents",
        json={
            "source_id": source_id,
            "title": "Wrong Source",
            "content_hash": "sha256:eeeeeeee",
            "source_uri": "upload://wrong-source",
            "size_bytes": 1,
        },
        headers=documents_admin_headers,
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Source does not belong to domain"
