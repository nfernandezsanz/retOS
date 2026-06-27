from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import anyio
from sqlalchemy.exc import IntegrityError

from retos.api.routes.events import progress_store
from retos.domain.documents import Document, DocumentVersion, Segment
from retos.ingestion.scan import SUPPORTED_SOURCE_SUFFIXES, SourceScanError, extract_source_text
from retos.ingestion.text import chunk_text, content_hash
from retos.persistence.unit_of_work import SQLAlchemyUnitOfWork


@dataclass(frozen=True)
class FileUploadIngestionResult:
    document: Document
    version: DocumentVersion
    segments: tuple[Segment, ...]


class FileUploadIngestionError(RuntimeError):
    pass


def sanitize_upload_filename(filename: str) -> str:
    cleaned = "".join(
        character if character.isalnum() or character in (".", "-", "_") else "-"
        for character in Path(filename).name.strip()
    )
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    if not cleaned or cleaned in {".", ".."}:
        raise FileUploadIngestionError("Upload filename is required")
    if Path(cleaned).suffix.lower() not in SUPPORTED_SOURCE_SUFFIXES:
        raise FileUploadIngestionError("Upload file type is not supported")
    return cleaned[:255]


async def run_file_upload_ingestion(
    *,
    job_id: str,
    uow: SQLAlchemyUnitOfWork,
    actor: str = "system:worker",
) -> FileUploadIngestionResult:
    started_at = datetime.now(UTC)
    async with uow:
        job = await uow.jobs.get(job_id)
        if job is None:
            raise FileUploadIngestionError("Job not found")
        if job.kind != "ingest.source":
            raise FileUploadIngestionError(f"Unsupported upload job kind: {job.kind}")
        if job.status != "queued":
            raise FileUploadIngestionError(f"Job must be queued, got {job.status}")
        if job.domain_id is None:
            raise FileUploadIngestionError("Upload job requires a domain_id")
        if job.payload.get("ingestion_kind") != "file_upload":
            raise FileUploadIngestionError("Upload job requires ingestion_kind=file_upload")

        source = None
        if job.source_id is not None:
            source = await uow.sources.get(job.source_id)
            if source is None:
                raise FileUploadIngestionError("Source not found")
            if source.domain_id != job.domain_id:
                raise FileUploadIngestionError("Source does not belong to job domain")

        file_path_value = job.payload.get("file_path")
        filename_value = job.payload.get("filename")
        source_uri_value = job.payload.get("source_uri")
        if not isinstance(file_path_value, str) or not isinstance(filename_value, str):
            raise FileUploadIngestionError("Upload job requires file_path and filename")
        if not isinstance(source_uri_value, str):
            raise FileUploadIngestionError("Upload job requires source_uri")

        file_path = Path(file_path_value)
        anyio_file_path = anyio.Path(file_path)
        if not await anyio_file_path.exists() or not await anyio_file_path.is_file():
            raise FileUploadIngestionError("Uploaded file is missing")

        max_bytes = int(job.payload.get("max_bytes") or 2_000_000)
        max_segment_tokens = int(job.payload.get("max_segment_tokens") or 220)
        enable_ocr = bool(job.payload.get("enable_ocr", True))
        max_ocr_pages = int(job.payload.get("max_ocr_pages") or 20)
        if max_bytes < 1:
            raise FileUploadIngestionError("max_bytes must be positive")
        if max_segment_tokens < 1:
            raise FileUploadIngestionError("max_segment_tokens must be positive")
        if max_ocr_pages < 1:
            raise FileUploadIngestionError("max_ocr_pages must be positive")

        try:
            text, raw, artifact_kind, extraction_kind = extract_source_text(
                file_path,
                max_bytes=max_bytes,
                enable_ocr=enable_ocr,
                max_ocr_pages=max_ocr_pages,
            )
        except SourceScanError as exc:
            raise FileUploadIngestionError(str(exc)) from exc

        file_hash = content_hash(raw)
        existing = await uow.documents.get_by_domain_and_hash(job.domain_id, file_hash)
        if existing is not None:
            raise FileUploadIngestionError("Document content hash already exists for domain")

        await uow.jobs.update_status(job_id=job.id, status="running", started_at=started_at)
        await uow.journal_events.add(
            actor=actor,
            event_type="job.running",
            entity_type="job",
            entity_id=job.id,
            payload={"from_status": job.status, "to_status": "running"},
        )
        await uow.progress_events.add(
            job_id=job.id,
            event_type="upload.started",
            message=f"Started upload ingestion for {filename_value}",
            payload={"filename": filename_value, "source_uri": source_uri_value},
        )

        title = str(job.payload.get("title") or Path(filename_value).stem)
        document, version = await uow.documents.add_with_initial_version(
            domain_id=job.domain_id,
            source_id=job.source_id,
            external_id=filename_value,
            title=title,
            content_hash=file_hash,
            metadata={
                "ingestion": {
                    "kind": "file_upload",
                    "job_id": job.id,
                    "source_id": source.id if source else None,
                    "filename": filename_value,
                    "suffix": Path(filename_value).suffix.lower(),
                    "extraction": extraction_kind,
                    "segmenter": "word-window-v1",
                }
            },
            source_uri=source_uri_value,
            size_bytes=len(raw),
        )
        artifact = await uow.documents.add_artifact(
            document_version_id=version.id,
            kind=artifact_kind,
            uri=source_uri_value,
            sha256=file_hash,
            size_bytes=len(raw),
        )
        segments = tuple(
            [
                await uow.documents.add_segment(
                    document_version_id=version.id,
                    ordinal=draft.ordinal,
                    text=draft.text,
                    anchor=f"{filename_value}#word={draft.anchor.removeprefix('word=')}",
                    token_count=draft.token_count,
                    content_hash=draft.content_hash,
                )
                for draft in chunk_text(text, max_tokens=max_segment_tokens)
            ]
        )
        completed_at = datetime.now(UTC)
        completed_job = await uow.jobs.update_status(
            job_id=job.id,
            status="succeeded",
            completed_at=completed_at,
        )
        await uow.journal_events.add(
            actor=actor,
            event_type="document.ingested",
            entity_type="document",
            entity_id=document.id,
            payload={
                "job_id": job.id,
                "domain_id": job.domain_id,
                "source_id": job.source_id,
                "version_id": version.id,
                "artifact_id": artifact.id,
                "segment_count": len(segments),
                "content_hash": file_hash,
                "filename": filename_value,
            },
        )
        await uow.journal_events.add(
            actor=actor,
            event_type="job.succeeded",
            entity_type="job",
            entity_id=job.id,
            payload={"from_status": "running", "to_status": "succeeded"},
        )
        await uow.progress_events.add(
            job_id=job.id,
            event_type="upload.completed",
            message=f"Ingested upload {filename_value}",
            payload={
                "document_id": document.id,
                "document_version_id": version.id,
                "segment_count": len(segments),
            },
        )
        if completed_job is None:
            raise FileUploadIngestionError("Job disappeared during upload ingestion")
        try:
            await uow.commit()
        except IntegrityError as exc:
            raise FileUploadIngestionError("Upload ingestion could not be persisted") from exc

    progress_store.append(
        "upload.completed",
        {
            "job_id": job_id,
            "document_id": document.id,
            "document_version_id": version.id,
            "segment_count": len(segments),
        },
    )
    return FileUploadIngestionResult(document=document, version=version, segments=segments)


async def fail_file_upload_ingestion_job(
    *,
    job_id: str,
    uow: SQLAlchemyUnitOfWork,
    error: str,
    actor: str = "system:worker",
) -> None:
    completed_at = datetime.now(UTC)
    async with uow:
        job = await uow.jobs.get(job_id)
        if job is None:
            return
        await uow.jobs.update_status(
            job_id=job.id,
            status="failed",
            completed_at=completed_at,
            error=error,
        )
        await uow.journal_events.add(
            actor=actor,
            event_type="job.failed",
            entity_type="job",
            entity_id=job.id,
            payload={"error": error},
        )
        await uow.progress_events.add(
            job_id=job.id,
            event_type="upload.failed",
            message="Upload ingestion failed",
            payload={"error": error},
        )
        await uow.commit()

    progress_store.append("upload.failed", {"job_id": job_id, "error": error})
