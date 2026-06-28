from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from retos.api.app import create_app
from retos.core.config import Settings


@pytest.fixture
def domain_client(settings: Settings, tmp_path: Path) -> Iterator[TestClient]:
    db_path = tmp_path / "retos.db"
    local_settings = settings.model_copy(
        update={
            "database_url": f"sqlite+aiosqlite:///{db_path}",
            "database_create_all": True,
        }
    )
    with TestClient(create_app(local_settings)) as test_client:
        yield test_client


@pytest.fixture
def admin_headers(domain_client: TestClient) -> dict[str, str]:
    response = domain_client.post(
        "/auth/login",
        json={"email": "admin@retos.dev", "password": "test-admin-password"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_domains_require_admin_token(domain_client: TestClient) -> None:
    response = domain_client.get("/domains")

    assert response.status_code == 401


def test_create_and_list_domain(
    domain_client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    created = domain_client.post(
        "/domains",
        json={
            "slug": "legal-research",
            "name": "Legal Research",
            "description": "Contracts and regulatory filings.",
        },
        headers=admin_headers,
    )

    assert created.status_code == 201
    created_body = created.json()
    assert created_body["slug"] == "legal-research"
    assert created_body["name"] == "Legal Research"
    assert created_body["description"] == "Contracts and regulatory filings."
    assert created_body["id"]
    assert created_body["created_at"]
    assert created_body["updated_at"]

    listed = domain_client.get("/domains", headers=admin_headers)

    assert listed.status_code == 200
    assert [domain["slug"] for domain in listed.json()] == ["legal-research"]


def test_get_domain_rejects_missing_domain(
    domain_client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    response = domain_client.get("/domains/missing-domain", headers=admin_headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "Domain not found"


def test_rejects_duplicate_domain_slug(
    domain_client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    payload = {"slug": "finance", "name": "Finance"}

    first = domain_client.post("/domains", json=payload, headers=admin_headers)
    second = domain_client.post("/domains", json=payload, headers=admin_headers)

    assert first.status_code == 201
    assert second.status_code == 409


def test_create_and_list_domain_source(
    domain_client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    domain_response = domain_client.post(
        "/domains",
        json={"slug": "research", "name": "Research"},
        headers=admin_headers,
    )
    domain_id = domain_response.json()["id"]

    source_response = domain_client.post(
        f"/domains/{domain_id}/sources",
        json={
            "kind": "mount",
            "name": "Fixture corpus",
            "uri": "file:///corpus/research",
        },
        headers=admin_headers,
    )

    assert source_response.status_code == 201
    source = source_response.json()
    assert source["domain_id"] == domain_id
    assert source["kind"] == "mount"
    assert source["name"] == "Fixture corpus"
    assert source["uri"] == "file:///corpus/research"

    listed = domain_client.get(f"/domains/{domain_id}/sources", headers=admin_headers)
    assert listed.status_code == 200
    assert [item["uri"] for item in listed.json()] == ["file:///corpus/research"]


def test_list_sources_rejects_missing_domain(
    domain_client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    response = domain_client.get("/domains/missing-domain/sources", headers=admin_headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "Domain not found"


def test_rejects_duplicate_source_uri_within_domain(
    domain_client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    domain_response = domain_client.post(
        "/domains",
        json={"slug": "dup-source", "name": "Duplicate Source"},
        headers=admin_headers,
    )
    domain_id = domain_response.json()["id"]
    payload = {
        "kind": "upload",
        "name": "Upload",
        "uri": "upload://same-file",
    }

    first = domain_client.post(f"/domains/{domain_id}/sources", json=payload, headers=admin_headers)
    second = domain_client.post(
        f"/domains/{domain_id}/sources",
        json=payload,
        headers=admin_headers,
    )

    assert first.status_code == 201
    assert second.status_code == 409


def test_source_requires_existing_domain(
    domain_client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    response = domain_client.post(
        "/domains/missing/sources",
        json={"kind": "upload", "name": "Upload", "uri": "upload://missing"},
        headers=admin_headers,
    )

    assert response.status_code == 404


def test_viewer_domain_list_is_empty_without_grants(
    domain_client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    created_domain = domain_client.post(
        "/domains",
        json={"slug": "viewer-empty", "name": "Viewer Empty"},
        headers=admin_headers,
    )
    created_viewer = domain_client.post(
        "/admin/users",
        headers=admin_headers,
        json={
            "email": "domain-viewer@retos.dev",
            "password": "domain-viewer-password",
            "roles": ["viewer"],
        },
    )
    login = domain_client.post(
        "/auth/login",
        json={"email": "domain-viewer@retos.dev", "password": "domain-viewer-password"},
    )
    viewer_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    listed = domain_client.get("/domains", headers=viewer_headers)
    fetched = domain_client.get(f"/domains/{created_domain.json()['id']}", headers=viewer_headers)

    assert created_domain.status_code == 201
    assert created_viewer.status_code == 201
    assert login.status_code == 200
    assert listed.status_code == 200
    assert listed.json() == []
    assert fetched.status_code == 403


def test_viewer_domain_grant_allows_domain_and_sources(
    domain_client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    created_domain = domain_client.post(
        "/domains",
        json={"slug": "viewer-granted", "name": "Viewer Granted"},
        headers=admin_headers,
    )
    domain_id = created_domain.json()["id"]
    created_source = domain_client.post(
        f"/domains/{domain_id}/sources",
        json={"kind": "upload", "name": "Granted Upload", "uri": "upload://granted"},
        headers=admin_headers,
    )
    created_viewer = domain_client.post(
        "/admin/users",
        headers=admin_headers,
        json={
            "email": "granted-domain-viewer@retos.dev",
            "password": "granted-domain-viewer-password",
            "roles": ["viewer"],
        },
    )
    grant = domain_client.post(
        f"/admin/users/{created_viewer.json()['id']}/domain-grants",
        headers=admin_headers,
        json={"domain_id": domain_id},
    )
    login = domain_client.post(
        "/auth/login",
        json={
            "email": "granted-domain-viewer@retos.dev",
            "password": "granted-domain-viewer-password",
        },
    )
    viewer_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    listed = domain_client.get("/domains", headers=viewer_headers)
    fetched = domain_client.get(f"/domains/{domain_id}", headers=viewer_headers)
    sources = domain_client.get(f"/domains/{domain_id}/sources", headers=viewer_headers)

    assert created_domain.status_code == 201
    assert created_source.status_code == 201
    assert created_viewer.status_code == 201
    assert grant.status_code == 201
    assert login.status_code == 200
    assert [domain["id"] for domain in listed.json()] == [domain_id]
    assert fetched.status_code == 200
    assert fetched.json()["slug"] == "viewer-granted"
    assert sources.status_code == 200
    assert [source["uri"] for source in sources.json()] == ["upload://granted"]
