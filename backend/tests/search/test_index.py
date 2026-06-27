from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from retos.api.app import create_app
from retos.api.routes.search import enqueue_rebuild_index
from retos.core.config import Settings
from retos.domain.documents import utc_now
from retos.domain.jobs import Job
from retos.persistence.unit_of_work import SQLAlchemyUnitOfWork
from retos.search.index import IndexedSegment, SearchIndexMissingError, TantivySearchIndex
from retos.search.service import fail_index_job


@pytest.fixture
def search_client(settings: Settings, tmp_path: Path) -> Iterator[TestClient]:
    local_settings = settings.model_copy(
        update={
            "database_url": f"sqlite+aiosqlite:///{tmp_path / 'retos-search.db'}",
            "database_create_all": True,
            "index_root": str(tmp_path / "index"),
        }
    )
    with TestClient(create_app(local_settings)) as test_client:
        yield test_client


@pytest.fixture
def search_admin_headers(search_client: TestClient) -> dict[str, str]:
    response = search_client.post(
        "/auth/login",
        json={"email": "admin@retos.dev", "password": "test-admin-password"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def create_search_fixture(
    client: TestClient,
    headers: dict[str, str],
) -> tuple[str, str]:
    domain_response = client.post(
        "/domains",
        json={"slug": "search-domain", "name": "Search Domain"},
        headers=headers,
    )
    domain_id = domain_response.json()["id"]
    source_response = client.post(
        f"/domains/{domain_id}/sources",
        json={"kind": "upload", "name": "Search source", "uri": "inline://search"},
        headers=headers,
    )
    source_id = source_response.json()["id"]
    document_response = client.post(
        f"/domains/{domain_id}/documents",
        json={
            "source_id": source_id,
            "title": "Lunar Mission Notes",
            "content_hash": "sha256:aaaaaaaa",
            "source_uri": "inline://search/lunar.txt",
            "size_bytes": 80,
        },
        headers=headers,
    )
    version_response = client.get(
        f"/documents/{document_response.json()['id']}/versions",
        headers=headers,
    )
    version_id = version_response.json()[0]["id"]
    for ordinal, text in enumerate(
        [
            "Apollo guidance computers used deterministic checklists.",
            "Ocean biology notes mention plankton and salinity.",
        ]
    ):
        client.post(
            f"/document-versions/{version_id}/segments",
            json={
                "ordinal": ordinal,
                "text": text,
                "anchor": f"paragraph={ordinal}",
                "token_count": len(text.split()),
                "content_hash": f"sha256:bbbbbbb{ordinal}",
            },
            headers=headers,
        )
    return domain_id, version_id


def test_tantivy_search_index_rebuilds_and_queries(tmp_path: Path) -> None:
    index = TantivySearchIndex(tmp_path)
    count = index.rebuild_domain(
        "domain-1",
        [
            IndexedSegment(
                segment_id="segment-1",
                document_id="document-1",
                document_version_id="version-1",
                title="Robotics",
                text="servo motors and control loops",
                anchor="paragraph=1",
                ordinal=0,
            )
        ],
    )

    hits = index.search_domain("domain-1", "servo", limit=5)

    assert count == 1
    assert hits[0].segment_id == "segment-1"
    assert hits[0].anchor == "paragraph=1"
    assert hits[0].score > 0


def test_tantivy_search_index_requires_rebuild(tmp_path: Path) -> None:
    with pytest.raises(SearchIndexMissingError):
        TantivySearchIndex(tmp_path).search_domain("missing", "query")


def test_enqueue_rebuild_index_dispatches_celery_task(monkeypatch: pytest.MonkeyPatch) -> None:
    delayed: list[str] = []
    now = utc_now()
    job = Job(
        id="job-idx",
        kind="index.domain",
        status="queued",
        domain_id="domain-idx",
        source_id=None,
        payload={},
        error=None,
        started_at=None,
        completed_at=None,
        created_at=now,
        updated_at=now,
    )
    monkeypatch.setattr(
        "retos.api.routes.search.rebuild_domain_index_job.delay",
        lambda job_id: delayed.append(job_id),
    )

    enqueue_rebuild_index(job)

    assert delayed == ["job-idx"]


def test_search_requires_existing_index(
    search_client: TestClient,
    search_admin_headers: dict[str, str],
) -> None:
    domain_id, _ = create_search_fixture(search_client, search_admin_headers)

    response = search_client.get(
        f"/domains/{domain_id}/search",
        params={"q": "apollo"},
        headers=search_admin_headers,
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Search index has not been built for this domain"


def test_rebuild_index_and_search_domain_inline(
    search_client: TestClient,
    search_admin_headers: dict[str, str],
) -> None:
    domain_id, _ = create_search_fixture(search_client, search_admin_headers)

    rebuild = search_client.post(
        f"/domains/{domain_id}/index/rebuild",
        json={"run_inline": True},
        headers=search_admin_headers,
    )
    assert rebuild.status_code == 202
    assert rebuild.json()["kind"] == "index.domain"
    assert rebuild.json()["status"] == "succeeded"

    response = search_client.get(
        f"/domains/{domain_id}/search",
        params={"q": "apollo guidance", "limit": 5},
        headers=search_admin_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "apollo guidance"
    assert body["hits"][0]["title"] == "Lunar Mission Notes"
    assert body["hits"][0]["anchor"] == "paragraph=0"
    assert "Apollo guidance" in body["hits"][0]["text"]


def test_rebuild_index_rejects_missing_domain(
    search_client: TestClient,
    search_admin_headers: dict[str, str],
) -> None:
    response = search_client.post(
        "/domains/missing/index/rebuild",
        json={"run_inline": True},
        headers=search_admin_headers,
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_fail_index_job_marks_job_failed(
    search_client: TestClient,
    search_admin_headers: dict[str, str],
) -> None:
    domain_id, _ = create_search_fixture(search_client, search_admin_headers)
    created_job = search_client.post(
        "/jobs",
        headers=search_admin_headers,
        json={"kind": "index.domain", "domain_id": domain_id, "payload": {}},
    )
    job_id = created_job.json()["id"]

    await fail_index_job(
        job_id=job_id,
        uow=SQLAlchemyUnitOfWork(search_client.app.state.session_factory),
        error="index exploded",
        actor="test-suite",
    )

    fetched = search_client.get(f"/jobs/{job_id}", headers=search_admin_headers)
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "failed"
    assert fetched.json()["error"] == "index exploded"
