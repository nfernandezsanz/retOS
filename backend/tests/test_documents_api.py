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


def count_document_side_effects(db_path: Path) -> tuple[int, int, int, int, int]:
    connection = sqlite3.connect(db_path)
    try:
        versions = connection.execute("select count(*) from document_versions").fetchone()[0]
        artifacts = connection.execute("select count(*) from artifacts").fetchone()[0]
        segments = connection.execute("select count(*) from segments").fetchone()[0]
        journals = connection.execute("select count(*) from journal_events").fetchone()[0]
        progress = connection.execute("select count(*) from progress_events").fetchone()[0]
        return int(versions), int(artifacts), int(segments), int(journals), int(progress)
    finally:
        connection.close()


def count_events(db_path: Path, table: str, event_type: str) -> int:
    queries = {
        "journal_events": "select count(*) from journal_events where event_type = ?",
        "progress_events": "select count(*) from progress_events where event_type = ?",
    }
    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute(queries[table], (event_type,)).fetchone()
        return int(row[0])
    finally:
        connection.close()


def create_document(
    client: TestClient,
    headers: dict[str, str],
    domain_id: str,
    source_id: str,
    *,
    content_hash: str = "sha256:abc12345",
) -> tuple[str, str]:
    created = client.post(
        f"/domains/{domain_id}/documents",
        json={
            "source_id": source_id,
            "external_id": "fixture-001",
            "title": "Fixture Document",
            "content_hash": content_hash,
            "source_uri": "upload://documents-domain/fixture.txt",
            "size_bytes": 128,
            "metadata": {"language": "en"},
        },
        headers=headers,
    )
    document_id = created.json()["id"]
    versions = client.get(f"/documents/{document_id}/versions", headers=headers)
    return document_id, versions.json()[0]["id"]


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
    assert document["archived_at"] is None

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

    assert count_document_side_effects(documents_db_path) == (1, 0, 0, 1, 1)


def test_update_document_title_and_metadata_is_audited(
    documents_client: TestClient,
    documents_admin_headers: dict[str, str],
    documents_db_path: Path,
) -> None:
    domain_id, source_id = create_domain_and_source(documents_client, documents_admin_headers)
    document_id, _ = create_document(
        documents_client,
        documents_admin_headers,
        domain_id,
        source_id,
    )

    updated = documents_client.patch(
        f"/documents/{document_id}",
        json={
            "title": "Reviewed Fixture Document",
            "metadata": {"language": "en", "reviewed": True},
        },
        headers=documents_admin_headers,
    )

    assert updated.status_code == 200
    payload = updated.json()
    assert payload["id"] == document_id
    assert payload["title"] == "Reviewed Fixture Document"
    assert payload["metadata"] == {"language": "en", "reviewed": True}
    assert payload["archived_at"] is None

    fetched = documents_client.get(f"/documents/{document_id}", headers=documents_admin_headers)
    assert fetched.status_code == 200
    assert fetched.json()["title"] == "Reviewed Fixture Document"
    assert count_events(documents_db_path, "journal_events", "document.updated") == 1
    assert count_events(documents_db_path, "progress_events", "document.updated") == 1


def test_update_document_rejects_empty_patch(
    documents_client: TestClient,
    documents_admin_headers: dict[str, str],
) -> None:
    domain_id, source_id = create_domain_and_source(documents_client, documents_admin_headers)
    document_id, _ = create_document(
        documents_client,
        documents_admin_headers,
        domain_id,
        source_id,
    )

    response = documents_client.patch(
        f"/documents/{document_id}",
        json={},
        headers=documents_admin_headers,
    )

    assert response.status_code == 422


def test_archive_document_hides_default_list_and_preserves_audit(
    documents_client: TestClient,
    documents_admin_headers: dict[str, str],
    documents_db_path: Path,
) -> None:
    domain_id, source_id = create_domain_and_source(documents_client, documents_admin_headers)
    document_id, _ = create_document(
        documents_client,
        documents_admin_headers,
        domain_id,
        source_id,
    )

    archived = documents_client.delete(
        f"/documents/{document_id}",
        headers=documents_admin_headers,
    )

    assert archived.status_code == 200
    archived_document = archived.json()
    assert archived_document["id"] == document_id
    assert archived_document["archived_at"] is not None

    default_list = documents_client.get(
        f"/domains/{domain_id}/documents",
        headers=documents_admin_headers,
    )
    assert default_list.status_code == 200
    assert default_list.json() == []

    archived_list = documents_client.get(
        f"/domains/{domain_id}/documents?include_archived=true",
        headers=documents_admin_headers,
    )
    assert archived_list.status_code == 200
    assert [item["id"] for item in archived_list.json()] == [document_id]

    second_archive = documents_client.delete(
        f"/documents/{document_id}",
        headers=documents_admin_headers,
    )
    assert second_archive.status_code == 200
    assert second_archive.json()["archived_at"] is not None
    assert count_events(documents_db_path, "journal_events", "document.archived") == 1
    assert count_events(documents_db_path, "progress_events", "document.archived") == 1


def test_restore_document_returns_to_active_list_and_preserves_audit(
    documents_client: TestClient,
    documents_admin_headers: dict[str, str],
    documents_db_path: Path,
) -> None:
    domain_id, source_id = create_domain_and_source(documents_client, documents_admin_headers)
    document_id, _ = create_document(
        documents_client,
        documents_admin_headers,
        domain_id,
        source_id,
    )
    documents_client.delete(f"/documents/{document_id}", headers=documents_admin_headers)

    restored = documents_client.post(
        f"/documents/{document_id}/restore",
        headers=documents_admin_headers,
    )

    assert restored.status_code == 200
    assert restored.json()["id"] == document_id
    assert restored.json()["archived_at"] is None

    default_list = documents_client.get(
        f"/domains/{domain_id}/documents",
        headers=documents_admin_headers,
    )
    assert default_list.status_code == 200
    assert [item["id"] for item in default_list.json()] == [document_id]

    second_restore = documents_client.post(
        f"/documents/{document_id}/restore",
        headers=documents_admin_headers,
    )
    assert second_restore.status_code == 200
    assert second_restore.json()["archived_at"] is None
    assert count_events(documents_db_path, "journal_events", "document.restored") == 1
    assert count_events(documents_db_path, "progress_events", "document.restored") == 1


def test_update_archive_and_restore_require_existing_document(
    documents_client: TestClient,
    documents_admin_headers: dict[str, str],
) -> None:
    updated = documents_client.patch(
        "/documents/missing",
        json={"title": "Missing"},
        headers=documents_admin_headers,
    )
    archived = documents_client.delete("/documents/missing", headers=documents_admin_headers)
    restored = documents_client.post(
        "/documents/missing/restore",
        headers=documents_admin_headers,
    )

    assert updated.status_code == 404
    assert archived.status_code == 404
    assert restored.status_code == 404


def test_create_artifact_and_segment_for_document_version(
    documents_client: TestClient,
    documents_admin_headers: dict[str, str],
    documents_db_path: Path,
) -> None:
    domain_id, source_id = create_domain_and_source(documents_client, documents_admin_headers)
    _, version_id = create_document(
        documents_client,
        documents_admin_headers,
        domain_id,
        source_id,
    )

    artifact_response = documents_client.post(
        f"/document-versions/{version_id}/artifacts",
        json={
            "kind": "raw_text",
            "uri": "storage://documents/fixture/raw.txt",
            "sha256": "sha256:11111111",
            "size_bytes": 64,
        },
        headers=documents_admin_headers,
    )
    assert artifact_response.status_code == 201
    artifact = artifact_response.json()
    assert artifact["document_version_id"] == version_id
    assert artifact["kind"] == "raw_text"

    segment_response = documents_client.post(
        f"/document-versions/{version_id}/segments",
        json={
            "ordinal": 0,
            "text": "This is a searchable fixture segment.",
            "anchor": "page=1",
            "token_count": 7,
            "content_hash": "sha256:22222222",
        },
        headers=documents_admin_headers,
    )
    assert segment_response.status_code == 201
    segment = segment_response.json()
    assert segment["document_version_id"] == version_id
    assert segment["ordinal"] == 0
    assert segment["anchor"] == "page=1"

    artifacts = documents_client.get(
        f"/document-versions/{version_id}/artifacts",
        headers=documents_admin_headers,
    )
    assert artifacts.status_code == 200
    assert [item["id"] for item in artifacts.json()] == [artifact["id"]]

    segments = documents_client.get(
        f"/document-versions/{version_id}/segments",
        headers=documents_admin_headers,
    )
    assert segments.status_code == 200
    assert [item["id"] for item in segments.json()] == [segment["id"]]

    assert count_document_side_effects(documents_db_path) == (1, 1, 1, 3, 3)


def test_create_artifact_rejects_duplicate_kind_and_uri(
    documents_client: TestClient,
    documents_admin_headers: dict[str, str],
) -> None:
    domain_id, source_id = create_domain_and_source(documents_client, documents_admin_headers)
    _, version_id = create_document(
        documents_client,
        documents_admin_headers,
        domain_id,
        source_id,
    )
    payload = {
        "kind": "ocr_text",
        "uri": "storage://documents/fixture/ocr.txt",
        "sha256": "sha256:33333333",
        "size_bytes": 12,
    }

    first = documents_client.post(
        f"/document-versions/{version_id}/artifacts",
        json=payload,
        headers=documents_admin_headers,
    )
    second = documents_client.post(
        f"/document-versions/{version_id}/artifacts",
        json=payload,
        headers=documents_admin_headers,
    )

    assert first.status_code == 201
    assert second.status_code == 409


def test_create_segment_rejects_duplicate_ordinal(
    documents_client: TestClient,
    documents_admin_headers: dict[str, str],
) -> None:
    domain_id, source_id = create_domain_and_source(documents_client, documents_admin_headers)
    _, version_id = create_document(
        documents_client,
        documents_admin_headers,
        domain_id,
        source_id,
    )
    payload = {
        "ordinal": 3,
        "text": "Repeated ordinal.",
        "token_count": 2,
        "content_hash": "sha256:44444444",
    }

    first = documents_client.post(
        f"/document-versions/{version_id}/segments",
        json=payload,
        headers=documents_admin_headers,
    )
    second = documents_client.post(
        f"/document-versions/{version_id}/segments",
        json=payload,
        headers=documents_admin_headers,
    )

    assert first.status_code == 201
    assert second.status_code == 409


def test_artifacts_and_segments_require_existing_version(
    documents_client: TestClient,
    documents_admin_headers: dict[str, str],
) -> None:
    artifact = documents_client.post(
        "/document-versions/missing/artifacts",
        json={
            "kind": "raw_text",
            "uri": "storage://missing",
            "sha256": "sha256:55555555",
            "size_bytes": 1,
        },
        headers=documents_admin_headers,
    )
    segment = documents_client.get(
        "/document-versions/missing/segments",
        headers=documents_admin_headers,
    )

    assert artifact.status_code == 404
    assert segment.status_code == 404


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
