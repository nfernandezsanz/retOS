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
    DomainUpdate,
    SourceCreate,
    SourceUpdate,
    archive_domain,
    create_domain,
    create_source,
    delete_source,
    list_domains,
    restore_domain,
    update_domain,
    update_source,
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
        archived_at=None,
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
            archived_at=None,
            created_at=NOW,
            updated_at=NOW,
        )
        return self.domain

    async def list(self, *, include_archived: bool = False) -> list[Domain]:
        if self.domain is None:
            return []
        if self.domain.archived_at is not None and not include_archived:
            return []
        return [self.domain]

    async def list_for_admin_user(
        self,
        admin_id: str,
        *,
        include_archived: bool = False,
    ) -> list[Domain]:
        return await self.list(include_archived=include_archived)

    async def get(self, domain_id: str) -> Domain | None:
        return self.domain if self.domain is not None and self.domain.id == domain_id else None

    async def update_details(
        self,
        *,
        domain_id: str,
        name: str,
        description: str | None,
    ) -> Domain | None:
        if self.domain is None or self.domain.id != domain_id:
            return None
        self.domain = Domain(
            id=self.domain.id,
            slug=self.domain.slug,
            name=name,
            description=description,
            archived_at=self.domain.archived_at,
            created_at=self.domain.created_at,
            updated_at=NOW,
        )
        return self.domain

    async def archive(self, domain_id: str) -> Domain | None:
        if self.domain is None or self.domain.id != domain_id:
            return None
        self.domain = Domain(
            id=self.domain.id,
            slug=self.domain.slug,
            name=self.domain.name,
            description=self.domain.description,
            archived_at=NOW,
            created_at=self.domain.created_at,
            updated_at=NOW,
        )
        return self.domain

    async def restore(self, domain_id: str) -> Domain | None:
        if self.domain is None or self.domain.id != domain_id:
            return None
        self.domain = Domain(
            id=self.domain.id,
            slug=self.domain.slug,
            name=self.domain.name,
            description=self.domain.description,
            archived_at=None,
            created_at=self.domain.created_at,
            updated_at=NOW,
        )
        return self.domain


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

    async def get(self, source_id: str) -> Source | None:
        return self.source if self.source is not None and self.source.id == source_id else None

    async def update_details(
        self,
        *,
        source_id: str,
        kind: str,
        name: str,
        uri: str,
    ) -> Source | None:
        if self.source is None or self.source.id != source_id:
            return None
        self.source = Source(
            id=self.source.id,
            domain_id=self.source.domain_id,
            kind=kind,  # type: ignore[arg-type]
            name=name,
            uri=uri,
            created_at=self.source.created_at,
            updated_at=NOW,
        )
        return self.source

    async def delete(self, source_id: str) -> Source | None:
        if self.source is None or self.source.id != source_id:
            return None
        source = self.source
        self.source = None
        return source


class FakeJournalEvents:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    async def add(
        self,
        *,
        actor: str,
        event_type: str,
        entity_type: str,
        entity_id: str,
        payload: dict[str, object],
    ) -> object:
        self.events.append(
            {
                "actor": actor,
                "event_type": event_type,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "payload": payload,
            }
        )
        return object()


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
        self.journal_events = FakeJournalEvents()
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


def test_update_domain_details_records_audit_event(
    domain_client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    created = domain_client.post(
        "/domains",
        json={
            "slug": "policy",
            "name": "Policy",
            "description": "Initial boundary.",
        },
        headers=admin_headers,
    )
    domain_id = created.json()["id"]

    updated = domain_client.patch(
        f"/domains/{domain_id}",
        json={
            "name": "Policy Review",
            "description": "Updated scope and retention boundary.",
        },
        headers=admin_headers,
    )
    fetched = domain_client.get(f"/domains/{domain_id}", headers=admin_headers)
    audit_events = domain_client.get("/audit/journal-events", headers=admin_headers)

    assert created.status_code == 201
    assert updated.status_code == 200
    assert updated.json()["slug"] == "policy"
    assert updated.json()["name"] == "Policy Review"
    assert updated.json()["description"] == "Updated scope and retention boundary."
    assert fetched.json()["name"] == "Policy Review"
    event = next(event for event in audit_events.json() if event["event_type"] == "domain.updated")
    assert event["entity_type"] == "domain"
    assert event["entity_id"] == domain_id
    assert event["payload"]["slug"] == "policy"
    assert {
        "field": "name",
        "before": "Policy",
        "after": "Policy Review",
    } in event[
        "payload"
    ]["changes"]
    assert {
        "field": "description",
        "before": "Initial boundary.",
        "after": "Updated scope and retention boundary.",
    } in event["payload"]["changes"]


def test_update_domain_requires_admin(
    domain_client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    created = domain_client.post(
        "/domains",
        json={"slug": "viewer-edit", "name": "Viewer Edit"},
        headers=admin_headers,
    )
    created_viewer = domain_client.post(
        "/admin/users",
        headers=admin_headers,
        json={
            "email": "domain-editor-viewer@retos.dev",
            "password": "domain-editor-viewer-password",
            "roles": ["viewer"],
        },
    )
    login = domain_client.post(
        "/auth/login",
        json={
            "email": "domain-editor-viewer@retos.dev",
            "password": "domain-editor-viewer-password",
        },
    )
    viewer_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = domain_client.patch(
        f"/domains/{created.json()['id']}",
        json={"name": "Nope", "description": None},
        headers=viewer_headers,
    )

    assert created.status_code == 201
    assert created_viewer.status_code == 201
    assert login.status_code == 200
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_update_domain_rejects_missing_domain() -> None:
    uow = FakeDomainUnitOfWork()

    with pytest.raises(HTTPException) as exc_info:
        await update_domain(
            DomainUpdate(name="Missing", description=None),
            actor="admin@retos.dev",
            uow=uow,  # type: ignore[arg-type]
            domain_id="missing-domain",
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Domain not found"


@pytest.mark.asyncio
async def test_update_domain_unit_records_changes() -> None:
    domain = domain_fixture()
    uow = FakeDomainUnitOfWork(domain=domain)

    updated = await update_domain(
        DomainUpdate(name="Domain Updated", description="New scope"),
        actor="admin@retos.dev",
        uow=uow,  # type: ignore[arg-type]
        domain_id=domain.id,
    )

    assert updated.name == "Domain Updated"
    assert uow.journal_events.events == [
        {
            "actor": "admin@retos.dev",
            "event_type": "domain.updated",
            "entity_type": "domain",
            "entity_id": domain.id,
            "payload": {
                "domain_id": domain.id,
                "slug": domain.slug,
                "changes": [
                    {
                        "field": "name",
                        "before": "Domain One",
                        "after": "Domain Updated",
                    },
                    {
                        "field": "description",
                        "before": None,
                        "after": "New scope",
                    },
                ],
            },
        }
    ]


def test_archive_and_restore_domain_records_audit_events(
    domain_client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    domain_response = domain_client.post(
        "/domains",
        json={"slug": "domain-archive", "name": "Domain Archive"},
        headers=admin_headers,
    )
    domain_id = domain_response.json()["id"]
    source_response = domain_client.post(
        f"/domains/{domain_id}/sources",
        json={"kind": "upload", "name": "Archive Source", "uri": "upload://archive-source"},
        headers=admin_headers,
    )
    domain_client.post(
        f"/domains/{domain_id}/documents",
        json={
            "source_id": source_response.json()["id"],
            "external_id": "archive-domain-doc",
            "title": "Archive Domain Document",
            "content_hash": "abcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcd",
            "source_uri": "upload://archive-source/document.txt",
            "size_bytes": 32,
            "metadata": {},
        },
        headers=admin_headers,
    )

    archived = domain_client.delete(f"/domains/{domain_id}", headers=admin_headers)
    listed = domain_client.get("/domains", headers=admin_headers)
    listed_with_archived = domain_client.get(
        "/domains?include_archived=true",
        headers=admin_headers,
    )
    sources = domain_client.get(f"/domains/{domain_id}/sources", headers=admin_headers)
    documents = domain_client.get(f"/domains/{domain_id}/documents", headers=admin_headers)
    restored = domain_client.post(f"/domains/{domain_id}/restore", headers=admin_headers)
    audit_events = domain_client.get("/audit/journal-events", headers=admin_headers)

    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None
    assert domain_id not in [domain["id"] for domain in listed.json()]
    assert domain_id in [domain["id"] for domain in listed_with_archived.json()]
    assert sources.status_code == 200
    assert sources.json()[0]["name"] == "Archive Source"
    assert documents.status_code == 200
    assert documents.json()[0]["title"] == "Archive Domain Document"
    assert restored.status_code == 200
    assert restored.json()["archived_at"] is None
    event_types = [event["event_type"] for event in audit_events.json()]
    assert "domain.archived" in event_types
    assert "domain.restored" in event_types


def test_archive_domain_requires_admin(
    domain_client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    domain_response = domain_client.post(
        "/domains",
        json={"slug": "domain-archive-viewer", "name": "Domain Archive Viewer"},
        headers=admin_headers,
    )
    domain_client.post(
        "/admin/users",
        headers=admin_headers,
        json={
            "email": "domain-archive-viewer@retos.dev",
            "password": "domain-archive-viewer-password",
            "roles": ["viewer"],
        },
    )
    login = domain_client.post(
        "/auth/login",
        json={
            "email": "domain-archive-viewer@retos.dev",
            "password": "domain-archive-viewer-password",
        },
    )
    viewer_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = domain_client.delete(
        f"/domains/{domain_response.json()['id']}",
        headers=viewer_headers,
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_archive_domain_rejects_missing_domain() -> None:
    uow = FakeDomainUnitOfWork()

    with pytest.raises(HTTPException) as exc_info:
        await archive_domain(
            actor="admin@retos.dev",
            uow=uow,  # type: ignore[arg-type]
            domain_id="missing-domain",
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Domain not found"


@pytest.mark.asyncio
async def test_restore_domain_rejects_missing_domain() -> None:
    uow = FakeDomainUnitOfWork()

    with pytest.raises(HTTPException) as exc_info:
        await restore_domain(
            actor="admin@retos.dev",
            uow=uow,  # type: ignore[arg-type]
            domain_id="missing-domain",
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Domain not found"


@pytest.mark.asyncio
async def test_archive_and_restore_domain_unit_records_changes() -> None:
    domain = domain_fixture()
    uow = FakeDomainUnitOfWork(domain=domain)

    archived = await archive_domain(
        actor="admin@retos.dev",
        uow=uow,  # type: ignore[arg-type]
        domain_id=domain.id,
    )
    restored = await restore_domain(
        actor="admin@retos.dev",
        uow=uow,  # type: ignore[arg-type]
        domain_id=domain.id,
    )

    assert archived.archived_at is not None
    assert restored.archived_at is None
    assert [event["event_type"] for event in uow.journal_events.events] == [
        "domain.archived",
        "domain.restored",
    ]
    assert uow.journal_events.events[0]["payload"] == {
        "domain_id": domain.id,
        "slug": domain.slug,
        "archived_at": NOW.isoformat(),
        "changes": [
            {
                "field": "archived_at",
                "before": None,
                "after": NOW.isoformat(),
            }
        ],
    }
    assert uow.journal_events.events[1]["payload"] == {
        "domain_id": domain.id,
        "slug": domain.slug,
        "changes": [
            {
                "field": "archived_at",
                "before": NOW.isoformat(),
                "after": None,
            }
        ],
    }


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


def test_update_source_details_records_audit_event(
    domain_client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    domain_response = domain_client.post(
        "/domains",
        json={"slug": "source-edit", "name": "Source Edit"},
        headers=admin_headers,
    )
    domain_id = domain_response.json()["id"]
    source_response = domain_client.post(
        f"/domains/{domain_id}/sources",
        json={
            "kind": "mount",
            "name": "Raw corpus",
            "uri": "file:///corpus/raw",
        },
        headers=admin_headers,
    )
    source_id = source_response.json()["id"]

    updated = domain_client.patch(
        f"/domains/{domain_id}/sources/{source_id}",
        json={
            "kind": "url",
            "name": "Reviewed corpus",
            "uri": "https://example.test/corpus",
        },
        headers=admin_headers,
    )
    listed = domain_client.get(f"/domains/{domain_id}/sources", headers=admin_headers)
    audit_events = domain_client.get("/audit/journal-events", headers=admin_headers)

    assert updated.status_code == 200
    assert updated.json()["kind"] == "url"
    assert updated.json()["name"] == "Reviewed corpus"
    assert updated.json()["uri"] == "https://example.test/corpus"
    assert [item["uri"] for item in listed.json()] == ["https://example.test/corpus"]
    event = next(event for event in audit_events.json() if event["event_type"] == "source.updated")
    assert event["entity_type"] == "source"
    assert event["entity_id"] == source_id
    assert event["payload"]["domain_id"] == domain_id
    assert {
        "field": "name",
        "before": "Raw corpus",
        "after": "Reviewed corpus",
    } in event[
        "payload"
    ]["changes"]
    assert {
        "field": "uri",
        "before": "file:///corpus/raw",
        "after": "https://example.test/corpus",
    } in event["payload"]["changes"]


def test_update_source_requires_admin(
    domain_client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    domain_response = domain_client.post(
        "/domains",
        json={"slug": "source-viewer-edit", "name": "Source Viewer Edit"},
        headers=admin_headers,
    )
    domain_id = domain_response.json()["id"]
    source_response = domain_client.post(
        f"/domains/{domain_id}/sources",
        json={"kind": "upload", "name": "Viewer Upload", "uri": "upload://viewer"},
        headers=admin_headers,
    )
    domain_client.post(
        "/admin/users",
        headers=admin_headers,
        json={
            "email": "source-editor-viewer@retos.dev",
            "password": "source-editor-viewer-password",
            "roles": ["viewer"],
        },
    )
    login = domain_client.post(
        "/auth/login",
        json={
            "email": "source-editor-viewer@retos.dev",
            "password": "source-editor-viewer-password",
        },
    )
    viewer_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = domain_client.patch(
        f"/domains/{domain_id}/sources/{source_response.json()['id']}",
        json={"kind": "upload", "name": "Nope", "uri": "upload://viewer-new"},
        headers=viewer_headers,
    )

    assert response.status_code == 403


def test_update_source_rejects_duplicate_uri(
    domain_client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    domain_response = domain_client.post(
        "/domains",
        json={"slug": "source-dup-update", "name": "Source Dup Update"},
        headers=admin_headers,
    )
    domain_id = domain_response.json()["id"]
    first = domain_client.post(
        f"/domains/{domain_id}/sources",
        json={"kind": "upload", "name": "First", "uri": "upload://first"},
        headers=admin_headers,
    )
    second = domain_client.post(
        f"/domains/{domain_id}/sources",
        json={"kind": "upload", "name": "Second", "uri": "upload://second"},
        headers=admin_headers,
    )

    response = domain_client.patch(
        f"/domains/{domain_id}/sources/{second.json()['id']}",
        json={"kind": "upload", "name": "Second renamed", "uri": "upload://first"},
        headers=admin_headers,
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert response.status_code == 409
    assert response.json()["detail"] == "Source URI already exists for domain"


def test_delete_source_records_audit_event_and_keeps_documents(
    domain_client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    domain_response = domain_client.post(
        "/domains",
        json={"slug": "source-delete", "name": "Source Delete"},
        headers=admin_headers,
    )
    domain_id = domain_response.json()["id"]
    source_response = domain_client.post(
        f"/domains/{domain_id}/sources",
        json={"kind": "upload", "name": "Delete Me", "uri": "upload://delete-me"},
        headers=admin_headers,
    )
    source_id = source_response.json()["id"]
    document_response = domain_client.post(
        f"/domains/{domain_id}/documents",
        json={
            "source_id": source_id,
            "external_id": "delete-source-doc",
            "title": "Delete Source Document",
            "content_hash": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
            "source_uri": "upload://delete-me/document.txt",
            "size_bytes": 32,
            "metadata": {},
        },
        headers=admin_headers,
    )

    deleted = domain_client.delete(
        f"/domains/{domain_id}/sources/{source_id}",
        headers=admin_headers,
    )
    listed_sources = domain_client.get(f"/domains/{domain_id}/sources", headers=admin_headers)
    listed_documents = domain_client.get(f"/domains/{domain_id}/documents", headers=admin_headers)
    audit_events = domain_client.get("/audit/journal-events", headers=admin_headers)

    assert document_response.status_code == 201
    assert deleted.status_code == 200
    assert deleted.json()["id"] == source_id
    assert listed_sources.status_code == 200
    assert listed_sources.json() == []
    assert listed_documents.status_code == 200
    assert listed_documents.json()[0]["title"] == "Delete Source Document"
    assert listed_documents.json()[0]["source_id"] is None
    event = next(event for event in audit_events.json() if event["event_type"] == "source.deleted")
    assert event["entity_type"] == "source"
    assert event["entity_id"] == source_id
    assert event["payload"] == {
        "domain_id": domain_id,
        "source_id": source_id,
        "kind": "upload",
        "name": "Delete Me",
        "uri": "upload://delete-me",
    }


def test_delete_source_requires_admin(
    domain_client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    domain_response = domain_client.post(
        "/domains",
        json={"slug": "source-delete-viewer", "name": "Source Delete Viewer"},
        headers=admin_headers,
    )
    domain_id = domain_response.json()["id"]
    source_response = domain_client.post(
        f"/domains/{domain_id}/sources",
        json={"kind": "upload", "name": "Viewer Delete", "uri": "upload://viewer-delete"},
        headers=admin_headers,
    )
    domain_client.post(
        "/admin/users",
        headers=admin_headers,
        json={
            "email": "source-delete-viewer@retos.dev",
            "password": "source-delete-viewer-password",
            "roles": ["viewer"],
        },
    )
    login = domain_client.post(
        "/auth/login",
        json={
            "email": "source-delete-viewer@retos.dev",
            "password": "source-delete-viewer-password",
        },
    )
    viewer_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = domain_client.delete(
        f"/domains/{domain_id}/sources/{source_response.json()['id']}",
        headers=viewer_headers,
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_update_source_rejects_missing_source() -> None:
    domain = domain_fixture()
    uow = FakeDomainUnitOfWork(domain=domain)

    with pytest.raises(HTTPException) as exc_info:
        await update_source(
            SourceUpdate(kind="upload", name="Missing", uri="upload://missing"),
            actor="admin@retos.dev",
            uow=uow,  # type: ignore[arg-type]
            domain_id=domain.id,
            source_id="missing-source",
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Source not found"


@pytest.mark.asyncio
async def test_update_source_rejects_missing_domain() -> None:
    uow = FakeDomainUnitOfWork()

    with pytest.raises(HTTPException) as exc_info:
        await update_source(
            SourceUpdate(kind="upload", name="Missing", uri="upload://missing"),
            actor="admin@retos.dev",
            uow=uow,  # type: ignore[arg-type]
            domain_id="missing-domain",
            source_id="missing-source",
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Domain not found"


@pytest.mark.asyncio
async def test_update_source_unit_records_changes() -> None:
    domain = domain_fixture()
    source = source_fixture(domain.id)
    uow = FakeDomainUnitOfWork(domain=domain, source=source)

    updated = await update_source(
        SourceUpdate(kind="mount", name="Mounted Source", uri="file:///updated"),
        actor="admin@retos.dev",
        uow=uow,  # type: ignore[arg-type]
        domain_id=domain.id,
        source_id=source.id,
    )

    assert updated.name == "Mounted Source"
    assert uow.journal_events.events == [
        {
            "actor": "admin@retos.dev",
            "event_type": "source.updated",
            "entity_type": "source",
            "entity_id": source.id,
            "payload": {
                "domain_id": domain.id,
                "source_id": source.id,
                "changes": [
                    {
                        "field": "kind",
                        "before": "upload",
                        "after": "mount",
                    },
                    {
                        "field": "name",
                        "before": "Source One",
                        "after": "Mounted Source",
                    },
                    {
                        "field": "uri",
                        "before": "upload://source-one",
                        "after": "file:///updated",
                    },
                ],
            },
        }
    ]


@pytest.mark.asyncio
async def test_update_source_rolls_integrity_race_into_conflict() -> None:
    domain = domain_fixture()
    source = source_fixture(domain.id)
    uow = FakeDomainUnitOfWork(domain=domain, source=source, fail_commit=True)

    with pytest.raises(HTTPException) as exc_info:
        await update_source(
            SourceUpdate(kind="upload", name="Source Race", uri="upload://source-race"),
            actor="admin@retos.dev",
            uow=uow,  # type: ignore[arg-type]
            domain_id=domain.id,
            source_id=source.id,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Source URI already exists for domain"


@pytest.mark.asyncio
async def test_delete_source_rejects_missing_domain() -> None:
    uow = FakeDomainUnitOfWork()

    with pytest.raises(HTTPException) as exc_info:
        await delete_source(
            actor="admin@retos.dev",
            uow=uow,  # type: ignore[arg-type]
            domain_id="missing-domain",
            source_id="missing-source",
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Domain not found"


@pytest.mark.asyncio
async def test_delete_source_rejects_missing_source() -> None:
    domain = domain_fixture()
    uow = FakeDomainUnitOfWork(domain=domain)

    with pytest.raises(HTTPException) as exc_info:
        await delete_source(
            actor="admin@retos.dev",
            uow=uow,  # type: ignore[arg-type]
            domain_id=domain.id,
            source_id="missing-source",
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Source not found"


@pytest.mark.asyncio
async def test_delete_source_unit_records_snapshot() -> None:
    domain = domain_fixture()
    source = source_fixture(domain.id)
    uow = FakeDomainUnitOfWork(domain=domain, source=source)

    deleted = await delete_source(
        actor="admin@retos.dev",
        uow=uow,  # type: ignore[arg-type]
        domain_id=domain.id,
        source_id=source.id,
    )

    assert deleted.id == source.id
    assert uow.sources.source is None
    assert uow.journal_events.events == [
        {
            "actor": "admin@retos.dev",
            "event_type": "source.deleted",
            "entity_type": "source",
            "entity_id": source.id,
            "payload": {
                "domain_id": domain.id,
                "source_id": source.id,
                "kind": "upload",
                "name": "Source One",
                "uri": "upload://source-one",
            },
        }
    ]


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
