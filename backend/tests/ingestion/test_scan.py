import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient

from retos.api.app import create_app
from retos.api.routes.ingestions import enqueue_source_scan
from retos.core.config import Settings
from retos.domain.documents import utc_now
from retos.domain.jobs import Job
from retos.ingestion.scan import (
    SourceScanError,
    extract_pdf_text,
    fail_source_scan_job,
    iter_supported_files,
    path_from_file_uri,
    read_text_file,
    run_source_scan,
)
from retos.persistence.unit_of_work import SQLAlchemyUnitOfWork


@pytest.fixture
def scan_db_path(tmp_path: Path) -> Path:
    return tmp_path / "retos-scan.db"


@pytest.fixture
def scan_client(settings: Settings, scan_db_path: Path) -> Iterator[TestClient]:
    local_settings = settings.model_copy(
        update={
            "database_url": f"sqlite+aiosqlite:///{scan_db_path}",
            "database_create_all": True,
        }
    )
    with TestClient(create_app(local_settings)) as test_client:
        yield test_client


@pytest.fixture
def scan_admin_headers(scan_client: TestClient) -> dict[str, str]:
    response = scan_client.post(
        "/auth/login",
        json={"email": "admin@retos.dev", "password": "test-admin-password"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def write_fixture_corpus(root: Path) -> None:
    root.mkdir(exist_ok=True)
    (root / "apollo-notes.txt").write_text(
        "Apollo guidance computers used deterministic checklists.",
        encoding="utf-8",
    )
    (root / "biology.md").write_text(
        "# Biology\n\nOcean biology notes mention plankton and salinity.",
        encoding="utf-8",
    )
    write_fixture_pdf(root / "mission-brief.pdf")


def write_fixture_pdf(path: Path) -> None:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Mars rover sample caching mission brief.")
    document.save(path)
    document.close()


def create_mount_source(
    client: TestClient,
    headers: dict[str, str],
    source_root: Path,
) -> tuple[str, str]:
    domain = client.post(
        "/domains",
        json={"slug": "scan-domain", "name": "Scan Domain"},
        headers=headers,
    )
    domain_id = domain.json()["id"]
    source = client.post(
        f"/domains/{domain_id}/sources",
        json={"kind": "mount", "name": "Mounted corpus", "uri": source_root.as_uri()},
        headers=headers,
    )
    return domain_id, source.json()["id"]


def count_scan_side_effects(db_path: Path) -> tuple[int, int, int, int, int]:
    connection = sqlite3.connect(db_path)
    try:
        documents = connection.execute("select count(*) from documents").fetchone()[0]
        versions = connection.execute("select count(*) from document_versions").fetchone()[0]
        artifacts = connection.execute("select count(*) from artifacts").fetchone()[0]
        segments = connection.execute("select count(*) from segments").fetchone()[0]
        jobs = connection.execute("select count(*) from jobs").fetchone()[0]
        return int(documents), int(versions), int(artifacts), int(segments), int(jobs)
    finally:
        connection.close()


def test_path_from_file_uri_rejects_unsupported_uri() -> None:
    with pytest.raises(SourceScanError, match="file://"):
        path_from_file_uri("https://example.test/corpus")


def test_path_from_file_uri_rejects_remote_authority() -> None:
    with pytest.raises(SourceScanError, match="Remote file authorities"):
        path_from_file_uri("file://fileserver/corpus")


def test_iter_supported_files_filters_text_and_markdown(tmp_path: Path) -> None:
    write_fixture_corpus(tmp_path)

    files = [path.name for path in iter_supported_files(tmp_path)]

    assert files == ["apollo-notes.txt", "biology.md", "mission-brief.pdf"]


def test_extract_pdf_text_reads_digital_pdf(tmp_path: Path) -> None:
    pdf_path = tmp_path / "fixture.pdf"
    write_fixture_pdf(pdf_path)

    text = extract_pdf_text(pdf_path.read_bytes())

    assert "Mars rover sample caching" in text


def test_iter_supported_files_accepts_single_supported_file(tmp_path: Path) -> None:
    single_file = tmp_path / "single.md"
    single_file.write_text("# Single", encoding="utf-8")

    assert list(iter_supported_files(single_file)) == [single_file]


def test_read_text_file_enforces_max_bytes(tmp_path: Path) -> None:
    too_large = tmp_path / "large.txt"
    too_large.write_text("abcdef", encoding="utf-8")

    with pytest.raises(SourceScanError, match="max_bytes"):
        read_text_file(too_large, max_bytes=3)


def test_enqueue_source_scan_dispatches_celery_task(monkeypatch: pytest.MonkeyPatch) -> None:
    delayed: list[str] = []
    now = utc_now()
    job = Job(
        id="job-scan",
        kind="ingest.source",
        status="queued",
        domain_id="domain-scan",
        source_id="source-scan",
        payload={},
        error=None,
        started_at=None,
        completed_at=None,
        created_at=now,
        updated_at=now,
    )
    monkeypatch.setattr(
        "retos.api.routes.ingestions.scan_source_job.delay",
        lambda job_id: delayed.append(job_id),
    )

    enqueue_source_scan(job)

    assert delayed == ["job-scan"]


def test_scan_source_endpoint_ingests_text_and_markdown_idempotently(
    scan_client: TestClient,
    scan_admin_headers: dict[str, str],
    scan_db_path: Path,
    tmp_path: Path,
) -> None:
    write_fixture_corpus(tmp_path)
    domain_id, source_id = create_mount_source(scan_client, scan_admin_headers, tmp_path)

    first = scan_client.post(
        f"/sources/{source_id}/scan",
        json={"max_segment_tokens": 20},
        headers=scan_admin_headers,
    )
    second = scan_client.post(
        f"/sources/{source_id}/scan",
        json={"max_segment_tokens": 20},
        headers=scan_admin_headers,
    )

    assert first.status_code == 202
    assert first.json()["status"] == "succeeded"
    assert second.status_code == 202
    assert second.json()["status"] == "succeeded"
    assert count_scan_side_effects(scan_db_path) == (3, 3, 3, 3, 2)

    documents = scan_client.get(f"/domains/{domain_id}/documents", headers=scan_admin_headers)
    assert documents.status_code == 200
    assert {item["external_id"] for item in documents.json()} == {
        "apollo-notes.txt",
        "biology.md",
        "mission-brief.pdf",
    }

    pdf_document = next(
        item for item in documents.json() if item["external_id"] == "mission-brief.pdf"
    )
    versions = scan_client.get(
        f"/documents/{pdf_document['id']}/versions",
        headers=scan_admin_headers,
    )
    artifacts = scan_client.get(
        f"/document-versions/{versions.json()[0]['id']}/artifacts",
        headers=scan_admin_headers,
    )
    assert artifacts.json()[0]["kind"] == "pdf_text"


@pytest.mark.asyncio
async def test_run_source_scan_respects_max_files(
    scan_client: TestClient,
    scan_admin_headers: dict[str, str],
    tmp_path: Path,
) -> None:
    write_fixture_corpus(tmp_path)
    domain_id, source_id = create_mount_source(scan_client, scan_admin_headers, tmp_path)
    created_job = scan_client.post(
        "/jobs",
        json={
            "kind": "ingest.source",
            "domain_id": domain_id,
            "source_id": source_id,
            "payload": {"max_files": 1, "max_segment_tokens": 20},
        },
        headers=scan_admin_headers,
    )

    result = await run_source_scan(
        job_id=created_job.json()["id"],
        uow=SQLAlchemyUnitOfWork(scan_client.app.state.session_factory),
        actor="test-suite",
    )

    assert result.scanned_files == 1
    assert result.created_documents == 1
    assert result.skipped_documents == 0


@pytest.mark.asyncio
async def test_run_source_scan_rejects_missing_path(
    scan_client: TestClient,
    scan_admin_headers: dict[str, str],
    tmp_path: Path,
) -> None:
    domain_id, source_id = create_mount_source(
        scan_client,
        scan_admin_headers,
        tmp_path / "missing",
    )
    created_job = scan_client.post(
        "/jobs",
        json={
            "kind": "ingest.source",
            "domain_id": domain_id,
            "source_id": source_id,
            "payload": {},
        },
        headers=scan_admin_headers,
    )

    with pytest.raises(SourceScanError, match="does not exist"):
        await run_source_scan(
            job_id=created_job.json()["id"],
            uow=SQLAlchemyUnitOfWork(scan_client.app.state.session_factory),
            actor="test-suite",
        )


@pytest.mark.asyncio
async def test_fail_source_scan_job_marks_job_failed(
    scan_client: TestClient,
    scan_admin_headers: dict[str, str],
    tmp_path: Path,
) -> None:
    write_fixture_corpus(tmp_path)
    domain_id, source_id = create_mount_source(scan_client, scan_admin_headers, tmp_path)
    created_job = scan_client.post(
        "/jobs",
        json={
            "kind": "ingest.source",
            "domain_id": domain_id,
            "source_id": source_id,
            "payload": {},
        },
        headers=scan_admin_headers,
    )
    job_id = created_job.json()["id"]

    await fail_source_scan_job(
        job_id=job_id,
        uow=SQLAlchemyUnitOfWork(scan_client.app.state.session_factory),
        error="scan failed",
        actor="test-suite",
    )

    fetched = scan_client.get(f"/jobs/{job_id}", headers=scan_admin_headers)
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "failed"
    assert fetched.json()["error"] == "scan failed"


def test_scan_source_endpoint_rejects_non_mount_sources(
    scan_client: TestClient,
    scan_admin_headers: dict[str, str],
) -> None:
    domain = scan_client.post(
        "/domains",
        json={"slug": "scan-upload", "name": "Upload Domain"},
        headers=scan_admin_headers,
    )
    source = scan_client.post(
        f"/domains/{domain.json()['id']}/sources",
        json={"kind": "upload", "name": "Upload", "uri": "upload://fixture"},
        headers=scan_admin_headers,
    )

    response = scan_client.post(
        f"/sources/{source.json()['id']}/scan",
        json={},
        headers=scan_admin_headers,
    )

    assert response.status_code == 422


def test_scan_source_endpoint_rejects_missing_source(
    scan_client: TestClient,
    scan_admin_headers: dict[str, str],
) -> None:
    response = scan_client.post(
        "/sources/missing/scan",
        json={},
        headers=scan_admin_headers,
    )

    assert response.status_code == 404


def test_scan_source_endpoint_can_queue_without_inline_in_development(
    settings: Settings,
    scan_db_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_fixture_corpus(tmp_path)
    local_settings = settings.model_copy(
        update={
            "env": "development",
            "database_url": f"sqlite+aiosqlite:///{scan_db_path}",
            "database_create_all": True,
        }
    )
    enqueued: list[str] = []
    monkeypatch.setattr(
        "retos.api.routes.ingestions.enqueue_source_scan",
        lambda job: enqueued.append(job.id),
    )
    with TestClient(create_app(local_settings)) as client:
        login = client.post(
            "/auth/login",
            json={"email": "admin@retos.dev", "password": "test-admin-password"},
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        _, source_id = create_mount_source(client, headers, tmp_path)

        response = client.post(
            f"/sources/{source_id}/scan",
            json={"run_inline": False},
            headers=headers,
        )

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert enqueued == [response.json()["id"]]
