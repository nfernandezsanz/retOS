from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from retos.api.app import create_app
from retos.api.routes.domains import (
    DomainCreate,
    SourceCreate,
    create_domain,
    create_source,
    list_domains,
)
from retos.core.config import Settings
from retos.domain.admin import AdminUser
from retos.domain.documents import Domain, Source


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


NOW = datetime(2026, 1, 1, tzinfo=UTC)


def domain_fixture(domain_id: str = "domain-1") -> Domain:
    return Domain(
        id=domain_id,
        slug="domain-one",
        name="Domain One",
        description=None,
        created_at=NOW,
        updated_at=NOW,
    )


def source_fixture(domain_id: str = "domain-1") -> Source:
    return Source(
        id="source-1",
        domain_id=domain_id,
        kind="upload",
        name="Source One",
        uri="upload://source-one",
        created_at=NOW,
        updated_at=NOW,
    )


class FakeAdminUsers:
    def __init__(self, admin: AdminUser | None = None) -> None:
        self.admin = admin

    async def get_by_email(self, email: str) -> AdminUser | None:
        return self.admin if self.admin is not None and self.admin.email == email else None


class FakeDomains:
    def __init__(self, domain: Domain | None = None) -> None:
        self.domain = domain

    async def get_by_slug(self, slug: str) -> Domain | None:
        return self.domain if self.domain is not None and self.domain.slug == slug else None

    async def add(self, *, slug: str, name: str, description: str | None) -> Domain:
        self.domain = Domain(
            id="domain-created",
            slug=slug,
            name=name,
            description=description,
            created_at=NOW,
            updated_at=NOW,
        )
        return self.domain

    async def list(self) -> list[Domain]:
        return [self.domain] if self.domain is not None else []

    async def list_for_admin_user(self, admin_id: str) -> list[Domain]:
        return [self.domain] if self.domain is not None else []

    async def get(self, domain_id: str) -> Domain | None:
        return self.domain if self.domain is not None and self.domain.id == domain_id else None


class FakeSources:
    def __init__(self, source: Source | None = None) -> None:
        self.source = source

    async def get_by_domain_and_uri(self, domain_id: str, uri: str) -> Source | None:
        if (
            self.source is not None
            and self.source.domain_id == domain_id
            and self.source.uri == uri
        ):
            return self.source
        return None

    async def add(self, *, domain_id: str, kind: str, name: str, uri: str) -> Source:
        self.source = Source(
            id="source-created",
            domain_id=domain_id,
            kind=kind,  # type: ignore[arg-type]
            name=name,
            uri=uri,
            created_at=NOW,
            updated_at=NOW,
        )
        return self.source


class FakeDomainUnitOfWork:
    def __init__(
        self,
        *,
        domain: Domain | None = None,
        source: Source | None = None,
        admin: AdminUser | None = None,
        fail_commit: bool = False,
    ) -> None:
        self.domains = FakeDomains(domain)
        self.sources = FakeSources(source)
        self.admin_users = FakeAdminUsers(admin)
        self.fail_commit = fail_commit

    async def __aenter__(self) -> FakeDomainUnitOfWork:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def commit(self) -> None:
        if self.fail_commit:
            raise IntegrityError("statement", {}, Exception("duplicate"))


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


@pytest.mark.asyncio
async def test_create_domain_rolls_integrity_race_into_conflict() -> None:
    uow = FakeDomainUnitOfWork(fail_commit=True)

    with pytest.raises(HTTPException) as exc_info:
        await create_domain(
            DomainCreate(slug="race-domain", name="Race Domain"),
            _="admin@retos.dev",
            uow=uow,  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Domain slug already exists"


@pytest.mark.asyncio
async def test_list_domains_returns_empty_for_unknown_authenticated_actor() -> None:
    uow = FakeDomainUnitOfWork(domain=domain_fixture())

    response = await list_domains(
        actor="missing-actor@retos.dev",
        uow=uow,  # type: ignore[arg-type]
    )

    assert response == []


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


@pytest.mark.asyncio
async def test_create_source_rolls_integrity_race_into_conflict() -> None:
    domain = domain_fixture("domain-race")
    uow = FakeDomainUnitOfWork(domain=domain, fail_commit=True)

    with pytest.raises(HTTPException) as exc_info:
        await create_source(
            SourceCreate(kind="upload", name="Race Source", uri="upload://race"),
            _="admin@retos.dev",
            uow=uow,  # type: ignore[arg-type]
            domain_id=domain.id,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Source URI already exists for domain"


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
