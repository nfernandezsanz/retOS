import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from fastapi.testclient import TestClient

from retos.api.app import create_app
from retos.api.routes.ingestions import enqueue_file_upload_ingestion
from retos.core.config import Settings
from retos.domain.documents import utc_now
from retos.domain.jobs import Job
from retos.ingestion.text import content_hash
from retos.ingestion.upload import (
    FileUploadIngestionError,
    fail_file_upload_ingestion_job,
    run_file_upload_ingestion,
    sanitize_upload_filename,
)
from retos.persistence.unit_of_work import SQLAlchemyUnitOfWork


@pytest.fixture
def upload_client(settings: Settings, tmp_path: Path) -> Iterator[TestClient]:
    local_settings = settings.model_copy(
        update={
            "database_url": f"sqlite+aiosqlite:///{tmp_path / 'retos-upload.db'}",
            "database_create_all": True,
            "storage_root": str(tmp_path / "storage"),
        }
    )
    with TestClient(create_app(local_settings)) as test_client:
        yield test_client


@pytest.fixture
def upload_admin_headers(upload_client: TestClient) -> dict[str, str]:
    response = upload_client.post(
        "/auth/login",
        json={"email": "admin@retos.dev", "password": "test-admin-password"},
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_upload_domain(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post(
        "/domains",
        headers=headers,
        json={"slug": "upload-domain", "name": "Upload Domain"},
    )
    assert response.status_code == 201
    return str(response.json()["id"])


def write_image_only_pdf(path: Path) -> None:
    document = pymupdf.open()
    document.new_page()
    document.save(path)
    document.close()


async def add_upload_job(
    client: TestClient,
    *,
    kind: str = "ingest.source",
    status: str = "queued",
    domain_id: str | None = None,
    source_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> str:
    async with SQLAlchemyUnitOfWork(client.app.state.session_factory) as uow:
        job = await uow.jobs.add(
            kind=kind,  # type: ignore[arg-type]
            status=status,  # type: ignore[arg-type]
            domain_id=domain_id,
            source_id=source_id,
            payload=payload if payload is not None else {"ingestion_kind": "file_upload"},
        )
        await uow.commit()
    return job.id


def test_sanitize_upload_filename_keeps_safe_supported_name() -> None:
    assert sanitize_upload_filename("../Mission Brief 01.pdf") == "Mission-Brief-01.pdf"


def test_sanitize_upload_filename_rejects_unsupported_suffix() -> None:
    with pytest.raises(FileUploadIngestionError, match="not supported"):
        sanitize_upload_filename("payload.exe")


def test_sanitize_upload_filename_rejects_empty_name() -> None:
    with pytest.raises(FileUploadIngestionError, match="required"):
        sanitize_upload_filename("   ")

    with pytest.raises(FileUploadIngestionError, match="required"):
        sanitize_upload_filename(".")


def test_enqueue_file_upload_ingestion_dispatches_celery_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delayed: list[str] = []
    now = utc_now()
    job = Job(
        id="job-upload",
        kind="ingest.source",
        status="queued",
        domain_id="domain-upload",
        source_id=None,
        payload={},
        error=None,
        started_at=None,
        completed_at=None,
        created_at=now,
        updated_at=now,
    )
    monkeypatch.setattr(
        "retos.api.routes.ingestions.ingest_file_upload_job.delay",
        lambda job_id: delayed.append(job_id),
    )

    enqueue_file_upload_ingestion(job)

    assert delayed == ["job-upload"]


def test_file_upload_endpoint_ingests_text_file_inline_in_test_env(
    upload_client: TestClient,
    upload_admin_headers: dict[str, str],
) -> None:
    domain_id = create_upload_domain(upload_client, upload_admin_headers)
    raw = b"Uploaded research note mentions carbon capture and audit trails."

    response = upload_client.post(
        f"/domains/{domain_id}/ingestions/upload",
        headers=upload_admin_headers,
        data={"title": "Uploaded Note", "max_segment_tokens": "20"},
        files={"file": ("uploaded note.txt", raw, "text/plain")},
    )

    assert response.status_code == 202
    job = response.json()
    assert job["kind"] == "ingest.source"
    assert job["status"] == "succeeded"
    assert job["payload"]["ingestion_kind"] == "file_upload"
    assert job["payload"]["filename"] == "uploaded-note.txt"
    assert job["payload"]["source_uri"].startswith(f"storage://uploads/{domain_id}/")

    documents = upload_client.get(
        f"/domains/{domain_id}/documents",
        headers=upload_admin_headers,
    )
    assert documents.status_code == 200
    [document] = documents.json()
    assert document["title"] == "Uploaded Note"
    assert document["external_id"] == "uploaded-note.txt"
    assert document["content_hash"] == content_hash(raw)
    assert document["metadata"]["ingestion"]["kind"] == "file_upload"

    versions = upload_client.get(
        f"/documents/{document['id']}/versions",
        headers=upload_admin_headers,
    )
    artifacts = upload_client.get(
        f"/document-versions/{versions.json()[0]['id']}/artifacts",
        headers=upload_admin_headers,
    )
    segments = upload_client.get(
        f"/document-versions/{versions.json()[0]['id']}/segments",
        headers=upload_admin_headers,
    )
    assert artifacts.json()[0]["kind"] == "raw_text"
    assert segments.json()[0]["anchor"] == "uploaded-note.txt#word=0"


def test_file_upload_endpoint_persists_ocr_page_artifacts(
    upload_client: TestClient,
    upload_admin_headers: dict[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    domain_id = create_upload_domain(upload_client, upload_admin_headers)
    pdf_path = tmp_path / "upload-scan.pdf"
    write_image_only_pdf(pdf_path)
    monkeypatch.setattr(
        "retos.ingestion.scan.pytesseract.image_to_string",
        lambda image, lang: "Uploaded OCR evidence",
    )

    response = upload_client.post(
        f"/domains/{domain_id}/ingestions/upload",
        headers=upload_admin_headers,
        data={"title": "Uploaded Scan", "max_segment_tokens": "20", "max_ocr_pages": "1"},
        files={"file": ("upload scan.pdf", pdf_path.read_bytes(), "application/pdf")},
    )

    assert response.status_code == 202
    documents = upload_client.get(
        f"/domains/{domain_id}/documents",
        headers=upload_admin_headers,
    )
    [document] = documents.json()
    assert document["metadata"]["ingestion"]["extraction"] == "pdf_ocr"
    assert document["metadata"]["ingestion"]["ocr_page_count"] == 1

    versions = upload_client.get(
        f"/documents/{document['id']}/versions",
        headers=upload_admin_headers,
    )
    artifacts = upload_client.get(
        f"/document-versions/{versions.json()[0]['id']}/artifacts",
        headers=upload_admin_headers,
    )
    artifact_payload = artifacts.json()
    assert [artifact["kind"] for artifact in artifact_payload] == ["ocr_page_text", "ocr_text"]
    assert artifact_payload[0]["uri"].endswith("#page=1")
    assert artifact_payload[1]["uri"].startswith(f"storage://uploads/{domain_id}/")


def test_file_upload_endpoint_rejects_missing_domain(
    upload_client: TestClient,
    upload_admin_headers: dict[str, str],
) -> None:
    response = upload_client.post(
        "/domains/missing-domain/ingestions/upload",
        headers=upload_admin_headers,
        files={"file": ("fixture.txt", b"no domain", "text/plain")},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Domain not found"


def test_file_upload_endpoint_rejects_missing_source(
    upload_client: TestClient,
    upload_admin_headers: dict[str, str],
) -> None:
    domain_id = create_upload_domain(upload_client, upload_admin_headers)

    response = upload_client.post(
        f"/domains/{domain_id}/ingestions/upload",
        headers=upload_admin_headers,
        data={"source_id": "missing-source"},
        files={"file": ("fixture.txt", b"missing source", "text/plain")},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Source not found"


def test_file_upload_endpoint_rejects_source_from_another_domain(
    upload_client: TestClient,
    upload_admin_headers: dict[str, str],
) -> None:
    domain_id = create_upload_domain(upload_client, upload_admin_headers)
    other_domain_id = upload_client.post(
        "/domains",
        headers=upload_admin_headers,
        json={"slug": "other-upload-domain", "name": "Other Upload Domain"},
    ).json()["id"]
    source_id = upload_client.post(
        f"/domains/{other_domain_id}/sources",
        headers=upload_admin_headers,
        json={"kind": "upload", "name": "Other source", "uri": "upload://other"},
    ).json()["id"]

    response = upload_client.post(
        f"/domains/{domain_id}/ingestions/upload",
        headers=upload_admin_headers,
        data={"source_id": source_id},
        files={"file": ("fixture.txt", b"wrong source", "text/plain")},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Source does not belong to domain"


def test_file_upload_endpoint_removes_file_when_max_bytes_exceeded(
    upload_client: TestClient,
    upload_admin_headers: dict[str, str],
    tmp_path: Path,
) -> None:
    domain_id = create_upload_domain(upload_client, upload_admin_headers)

    response = upload_client.post(
        f"/domains/{domain_id}/ingestions/upload",
        headers=upload_admin_headers,
        data={"max_bytes": "4"},
        files={"file": ("too-large.txt", b"too large", "text/plain")},
    )

    assert response.status_code == 413
    assert not list((tmp_path / "storage" / "uploads").glob("**/too-large.txt"))


def test_file_upload_endpoint_rejects_unsupported_file_type(
    upload_client: TestClient,
    upload_admin_headers: dict[str, str],
) -> None:
    domain_id = create_upload_domain(upload_client, upload_admin_headers)

    response = upload_client.post(
        f"/domains/{domain_id}/ingestions/upload",
        headers=upload_admin_headers,
        files={"file": ("malware.exe", b"nope", "application/octet-stream")},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Upload file type is not supported"


def test_file_upload_endpoint_marks_failed_when_inline_runner_crashes(
    upload_client: TestClient,
    upload_admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    domain_id = create_upload_domain(upload_client, upload_admin_headers)
    failures: list[dict[str, object]] = []

    async def broken_runner(**_: object) -> None:
        raise RuntimeError("inline upload crashed")

    async def fake_fail_job(**kwargs: object) -> None:
        failures.append(dict(kwargs))

    monkeypatch.setattr("retos.ingestion.upload.run_file_upload_ingestion", broken_runner)
    monkeypatch.setattr("retos.api.routes.ingestions.fail_file_upload_ingestion_job", fake_fail_job)

    response = upload_client.post(
        f"/domains/{domain_id}/ingestions/upload",
        headers=upload_admin_headers,
        files={"file": ("crash.txt", b"crash content", "text/plain")},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Upload ingestion failed"
    assert failures
    assert failures[0]["error"] == "inline upload crashed"


def test_file_upload_endpoint_can_queue_without_inline_in_development(
    settings: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_settings = settings.model_copy(
        update={
            "env": "development",
            "database_url": f"sqlite+aiosqlite:///{tmp_path / 'retos-upload-dev.db'}",
            "database_create_all": True,
            "storage_root": str(tmp_path / "storage"),
        }
    )
    enqueued: list[str] = []
    monkeypatch.setattr(
        "retos.api.routes.ingestions.enqueue_file_upload_ingestion",
        lambda job: enqueued.append(job.id),
    )
    with TestClient(create_app(local_settings)) as client:
        login = client.post(
            "/auth/login",
            json={"email": "admin@retos.dev", "password": "test-admin-password"},
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        domain_id = create_upload_domain(client, headers)

        response = client.post(
            f"/domains/{domain_id}/ingestions/upload",
            headers=headers,
            files={"file": ("queued.md", b"# queued", "text/markdown")},
        )

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert enqueued == [response.json()["id"]]


@pytest.mark.asyncio
async def test_run_file_upload_ingestion_rejects_duplicate_content(
    upload_client: TestClient,
    upload_admin_headers: dict[str, str],
    tmp_path: Path,
) -> None:
    domain_id = create_upload_domain(upload_client, upload_admin_headers)
    raw = b"Duplicate upload content."
    file_path = tmp_path / "duplicate.txt"
    file_path.write_bytes(raw)
    upload_client.post(
        f"/domains/{domain_id}/documents",
        headers=upload_admin_headers,
        json={
            "external_id": "existing",
            "title": "Existing",
            "content_hash": content_hash(raw),
            "source_uri": "upload://existing.txt",
            "size_bytes": len(raw),
        },
    )
    created_job = upload_client.post(
        "/jobs",
        headers=upload_admin_headers,
        json={
            "kind": "ingest.source",
            "domain_id": domain_id,
            "payload": {
                "ingestion_kind": "file_upload",
                "filename": "duplicate.txt",
                "file_path": str(file_path),
                "source_uri": "storage://uploads/duplicate.txt",
            },
        },
    )

    with pytest.raises(FileUploadIngestionError, match="already exists"):
        await run_file_upload_ingestion(
            job_id=created_job.json()["id"],
            uow=SQLAlchemyUnitOfWork(upload_client.app.state.session_factory),
        )


@pytest.mark.asyncio
async def test_run_file_upload_ingestion_rejects_missing_job(
    upload_client: TestClient,
) -> None:
    with pytest.raises(FileUploadIngestionError, match="Job not found"):
        await run_file_upload_ingestion(
            job_id="missing-job",
            uow=SQLAlchemyUnitOfWork(upload_client.app.state.session_factory),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("job_kwargs", "message"),
    [
        ({"kind": "index.domain"}, "Unsupported upload job kind"),
        ({"status": "running"}, "Job must be queued"),
        ({"domain_id": None}, "requires a domain_id"),
        ({"payload": {}}, "ingestion_kind=file_upload"),
        (
            {"payload": {"ingestion_kind": "file_upload", "filename": "fixture.txt"}},
            "file_path and filename",
        ),
        (
            {
                "payload": {
                    "ingestion_kind": "file_upload",
                    "filename": "fixture.txt",
                    "file_path": "missing.txt",
                }
            },
            "source_uri",
        ),
        (
            {
                "payload": {
                    "ingestion_kind": "file_upload",
                    "filename": "fixture.txt",
                    "file_path": "missing.txt",
                    "source_uri": "storage://missing",
                }
            },
            "missing",
        ),
    ],
)
async def test_run_file_upload_ingestion_rejects_invalid_job_payloads(
    upload_client: TestClient,
    upload_admin_headers: dict[str, str],
    job_kwargs: dict[str, Any],
    message: str,
) -> None:
    domain_id = create_upload_domain(upload_client, upload_admin_headers)
    job_kwargs.setdefault("domain_id", domain_id)
    job_id = await add_upload_job(upload_client, **job_kwargs)

    with pytest.raises(FileUploadIngestionError, match=message):
        await run_file_upload_ingestion(
            job_id=job_id,
            uow=SQLAlchemyUnitOfWork(upload_client.app.state.session_factory),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload_overrides", "message"),
    [
        ({"max_bytes": -1}, "max_bytes"),
        ({"max_segment_tokens": -1}, "max_segment_tokens"),
        ({"max_ocr_pages": -1}, "max_ocr_pages"),
    ],
)
async def test_run_file_upload_ingestion_rejects_invalid_numeric_limits(
    upload_client: TestClient,
    upload_admin_headers: dict[str, str],
    tmp_path: Path,
    payload_overrides: dict[str, int],
    message: str,
) -> None:
    domain_id = create_upload_domain(upload_client, upload_admin_headers)
    file_path = tmp_path / "fixture.txt"
    file_path.write_text("valid upload text", encoding="utf-8")
    payload = {
        "ingestion_kind": "file_upload",
        "filename": "fixture.txt",
        "file_path": str(file_path),
        "source_uri": "storage://uploads/fixture.txt",
        **payload_overrides,
    }
    job_id = await add_upload_job(upload_client, domain_id=domain_id, payload=payload)

    with pytest.raises(FileUploadIngestionError, match=message):
        await run_file_upload_ingestion(
            job_id=job_id,
            uow=SQLAlchemyUnitOfWork(upload_client.app.state.session_factory),
        )


@pytest.mark.asyncio
async def test_run_file_upload_ingestion_rejects_missing_source(
    upload_client: TestClient,
    upload_admin_headers: dict[str, str],
) -> None:
    domain_id = create_upload_domain(upload_client, upload_admin_headers)
    job_id = await add_upload_job(
        upload_client,
        domain_id=domain_id,
        source_id="missing-source",
        payload={"ingestion_kind": "file_upload"},
    )

    with pytest.raises(FileUploadIngestionError, match="Source not found"):
        await run_file_upload_ingestion(
            job_id=job_id,
            uow=SQLAlchemyUnitOfWork(upload_client.app.state.session_factory),
        )


@pytest.mark.asyncio
async def test_fail_file_upload_ingestion_job_marks_job_failed(
    upload_client: TestClient,
    upload_admin_headers: dict[str, str],
    tmp_path: Path,
) -> None:
    domain_id = create_upload_domain(upload_client, upload_admin_headers)
    created_job = upload_client.post(
        "/jobs",
        headers=upload_admin_headers,
        json={
            "kind": "ingest.source",
            "domain_id": domain_id,
            "payload": {"ingestion_kind": "file_upload"},
        },
    )
    job_id = created_job.json()["id"]

    await fail_file_upload_ingestion_job(
        job_id=job_id,
        uow=SQLAlchemyUnitOfWork(upload_client.app.state.session_factory),
        error="fixture failure",
        actor="test-suite",
    )

    failed_job = upload_client.get(f"/jobs/{job_id}", headers=upload_admin_headers)
    assert failed_job.json()["status"] == "failed"
    assert failed_job.json()["error"] == "fixture failure"

    connection = sqlite3.connect(tmp_path / "retos-upload.db")
    try:
        journal_count = connection.execute(
            "select count(*) from journal_events where event_type = 'job.failed'",
        ).fetchone()[0]
        progress_count = connection.execute(
            "select count(*) from progress_events where event_type = 'upload.failed'",
        ).fetchone()[0]
    finally:
        connection.close()
    assert journal_count == 1
    assert progress_count == 1


@pytest.mark.asyncio
async def test_fail_file_upload_ingestion_job_ignores_missing_job(
    upload_client: TestClient,
    tmp_path: Path,
) -> None:
    await fail_file_upload_ingestion_job(
        job_id="missing-job",
        uow=SQLAlchemyUnitOfWork(upload_client.app.state.session_factory),
        error="fixture failure",
    )

    connection = sqlite3.connect(tmp_path / "retos-upload.db")
    try:
        journal_count = connection.execute("select count(*) from journal_events").fetchone()[0]
        progress_count = connection.execute("select count(*) from progress_events").fetchone()[0]
    finally:
        connection.close()
    assert journal_count == 0
    assert progress_count == 0
