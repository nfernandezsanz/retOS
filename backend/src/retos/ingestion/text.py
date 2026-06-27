from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256

from sqlalchemy.exc import IntegrityError

from retos.api.routes.events import progress_store
from retos.domain.documents import Document, DocumentVersion, Segment
from retos.persistence.unit_of_work import SQLAlchemyUnitOfWork


@dataclass(frozen=True)
class TextSegmentDraft:
    ordinal: int
    text: str
    anchor: str
    token_count: int
    content_hash: str


@dataclass(frozen=True)
class TextIngestionResult:
    document: Document
    version: DocumentVersion
    segments: Sequence[Segment]


class TextIngestionError(RuntimeError):
    pass


def content_hash(content: str | bytes) -> str:
    raw = content if isinstance(content, bytes) else content.encode("utf-8")
    return f"sha256:{sha256(raw).hexdigest()}"


def chunk_text(text: str, *, max_tokens: int = 220) -> list[TextSegmentDraft]:
    normalized = " ".join(text.split())
    if not normalized:
        raise TextIngestionError("Text ingestion requires non-empty text")
    if max_tokens < 1:
        raise ValueError("max_tokens must be positive")

    words = normalized.split(" ")
    chunks: list[TextSegmentDraft] = []
    for ordinal, start in enumerate(range(0, len(words), max_tokens)):
        segment_words = words[start : start + max_tokens]
        segment_text = " ".join(segment_words)
        chunks.append(
            TextSegmentDraft(
                ordinal=ordinal,
                text=segment_text,
                anchor=f"word={start}",
                token_count=len(segment_words),
                content_hash=content_hash(segment_text),
            )
        )
    return chunks


async def run_text_ingestion(
    *,
    job_id: str,
    uow: SQLAlchemyUnitOfWork,
    actor: str = "system:worker",
) -> TextIngestionResult:
    started_at = datetime.now(UTC)
    async with uow:
        job = await uow.jobs.get(job_id)
        if job is None:
            raise TextIngestionError("Job not found")
        if job.kind != "ingest.source":
            raise TextIngestionError(f"Unsupported ingestion job kind: {job.kind}")
        if job.status != "queued":
            raise TextIngestionError(f"Job must be queued, got {job.status}")
        if job.domain_id is None:
            raise TextIngestionError("Ingestion job requires a domain_id")

        source = None
        if job.source_id is not None:
            source = await uow.sources.get(job.source_id)
            if source is None:
                raise TextIngestionError("Source not found")
            if source.domain_id != job.domain_id:
                raise TextIngestionError("Source does not belong to job domain")

        text = str(job.payload.get("text") or "")
        title = str(job.payload.get("title") or "Untitled text document")
        source_uri = str(
            job.payload.get("source_uri") or (source.uri if source else "inline://text")
        )
        external_id = job.payload.get("external_id")
        max_tokens = int(job.payload.get("max_segment_tokens") or 220)
        metadata = job.payload.get("metadata") or {}
        if not isinstance(metadata, dict):
            raise TextIngestionError("metadata must be an object")
        if external_id is not None and not isinstance(external_id, str):
            raise TextIngestionError("external_id must be a string")

        text_bytes = text.encode("utf-8")
        document_hash = content_hash(text_bytes)
        existing = await uow.documents.get_by_domain_and_hash(job.domain_id, document_hash)
        if existing is not None:
            raise TextIngestionError("Document content hash already exists for domain")

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
            event_type="ingestion.started",
            message=f"Started text ingestion for {title}",
            payload={"title": title, "source_uri": source_uri},
        )

        document, version = await uow.documents.add_with_initial_version(
            domain_id=job.domain_id,
            source_id=job.source_id,
            external_id=external_id,
            title=title,
            content_hash=document_hash,
            metadata={
                **metadata,
                "ingestion": {
                    "kind": "text",
                    "job_id": job.id,
                    "segmenter": "word-window-v1",
                },
            },
            source_uri=source_uri,
            size_bytes=len(text_bytes),
        )
        artifact = await uow.documents.add_artifact(
            document_version_id=version.id,
            kind="raw_text",
            uri=f"inline://jobs/{job.id}/raw.txt",
            sha256=document_hash,
            size_bytes=len(text_bytes),
        )
        segment_drafts = chunk_text(text, max_tokens=max_tokens)
        segments = [
            await uow.documents.add_segment(
                document_version_id=version.id,
                ordinal=draft.ordinal,
                text=draft.text,
                anchor=draft.anchor,
                token_count=draft.token_count,
                content_hash=draft.content_hash,
            )
            for draft in segment_drafts
        ]
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
                "content_hash": document_hash,
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
            event_type="ingestion.completed",
            message=f"Ingested {title}",
            payload={
                "document_id": document.id,
                "document_version_id": version.id,
                "segment_count": len(segments),
            },
        )
        if completed_job is None:
            raise TextIngestionError("Job disappeared during ingestion")
        try:
            await uow.commit()
        except IntegrityError as exc:
            raise TextIngestionError("Text ingestion could not be persisted") from exc

    progress_store.append(
        "ingestion.completed",
        {
            "job_id": job_id,
            "document_id": document.id,
            "document_version_id": version.id,
            "segment_count": len(segments),
        },
    )
    return TextIngestionResult(document=document, version=version, segments=segments)


async def fail_text_ingestion_job(
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
            event_type="ingestion.failed",
            message="Text ingestion failed",
            payload={"error": error},
        )
        await uow.commit()

    progress_store.append("ingestion.failed", {"job_id": job_id, "error": error})
