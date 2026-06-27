from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

import pymupdf
import pytesseract  # type: ignore[import-untyped]
from PIL import Image
from sqlalchemy.exc import IntegrityError

from retos.api.routes.events import progress_store
from retos.ingestion.text import chunk_text, content_hash
from retos.persistence.unit_of_work import SQLAlchemyUnitOfWork

SUPPORTED_SOURCE_SUFFIXES = frozenset({".txt", ".md", ".pdf"})


@dataclass(frozen=True)
class SourceScanResult:
    domain_id: str
    source_id: str
    scanned_files: int
    created_documents: int
    skipped_documents: int
    segment_count: int


class SourceScanError(RuntimeError):
    pass


def path_from_file_uri(uri: str) -> Path:
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        raise SourceScanError("Mounted source scans require a file:// URI")
    if parsed.netloc not in ("", "localhost"):
        raise SourceScanError("Remote file authorities are not supported")
    return Path(unquote(parsed.path)).resolve()


def iter_supported_files(root: Path) -> Iterable[Path]:
    if root.is_file():
        if root.suffix.lower() in SUPPORTED_SOURCE_SUFFIXES:
            yield root
        return
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in SUPPORTED_SOURCE_SUFFIXES:
            yield path


def read_text_file(path: Path, *, max_bytes: int) -> tuple[str, bytes]:
    raw = path.read_bytes()
    if len(raw) > max_bytes:
        raise SourceScanError(f"File exceeds max_bytes: {path}")
    return raw.decode("utf-8", errors="replace"), raw


def extract_pdf_text(raw: bytes) -> str:
    pages: list[str] = []
    with pymupdf.open(stream=raw, filetype="pdf") as document:  # type: ignore[no-untyped-call]
        for page in document:
            text = page.get_text("text").strip()
            if text:
                pages.append(text)
    if not pages:
        raise SourceScanError("PDF contains no extractable text")
    return "\n\n".join(pages)


def ocr_pdf_text(raw: bytes, *, max_pages: int) -> str:
    if max_pages < 1:
        raise SourceScanError("max_ocr_pages must be positive")

    pages: list[str] = []
    with pymupdf.open(stream=raw, filetype="pdf") as document:  # type: ignore[no-untyped-call]
        for page_number, page in enumerate(document):
            if page_number >= max_pages:
                break
            pixmap = page.get_pixmap(
                matrix=pymupdf.Matrix(2, 2),  # type: ignore[no-untyped-call]
                alpha=False,
            )
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            text = pytesseract.image_to_string(image, lang="eng").strip()
            if text:
                pages.append(text)
    if not pages:
        raise SourceScanError("PDF OCR produced no text")
    return "\n\n".join(pages)


def extract_pdf_content(
    raw: bytes,
    *,
    enable_ocr: bool,
    max_ocr_pages: int,
) -> tuple[str, str, str]:
    try:
        return extract_pdf_text(raw), "pdf_text", "pdf_text"
    except SourceScanError:
        if not enable_ocr:
            raise
    return ocr_pdf_text(raw, max_pages=max_ocr_pages), "ocr_text", "pdf_ocr"


def extract_source_text(
    path: Path,
    *,
    max_bytes: int,
    enable_ocr: bool = True,
    max_ocr_pages: int = 20,
) -> tuple[str, bytes, str, str]:
    raw = path.read_bytes()
    if len(raw) > max_bytes:
        raise SourceScanError(f"File exceeds max_bytes: {path}")
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        text, artifact_kind, extraction_kind = extract_pdf_content(
            raw,
            enable_ocr=enable_ocr,
            max_ocr_pages=max_ocr_pages,
        )
        return text, raw, artifact_kind, extraction_kind
    return raw.decode("utf-8", errors="replace"), raw, "raw_text", "raw_text"


async def run_source_scan(
    *,
    job_id: str,
    uow: SQLAlchemyUnitOfWork,
    actor: str = "system:worker",
) -> SourceScanResult:
    started_at = datetime.now(UTC)
    async with uow:
        job = await uow.jobs.get(job_id)
        if job is None:
            raise SourceScanError("Job not found")
        if job.kind != "ingest.source":
            raise SourceScanError(f"Unsupported scan job kind: {job.kind}")
        if job.status != "queued":
            raise SourceScanError(f"Job must be queued, got {job.status}")
        if job.domain_id is None or job.source_id is None:
            raise SourceScanError("Source scan jobs require domain_id and source_id")

        source = await uow.sources.get(job.source_id)
        if source is None:
            raise SourceScanError("Source not found")
        if source.domain_id != job.domain_id:
            raise SourceScanError("Source does not belong to job domain")
        if source.kind != "mount":
            raise SourceScanError("Source scan currently supports mount sources only")

        root = path_from_file_uri(source.uri)
        if not root.exists():
            raise SourceScanError("Source path does not exist")
        if not (root.is_dir() or root.is_file()):
            raise SourceScanError("Source path must be a file or directory")

        max_files = int(job.payload.get("max_files") or 500)
        max_bytes = int(job.payload.get("max_bytes") or 2_000_000)
        max_segment_tokens = int(job.payload.get("max_segment_tokens") or 220)
        enable_ocr = bool(job.payload.get("enable_ocr", True))
        max_ocr_pages = int(job.payload.get("max_ocr_pages") or 20)
        if max_files < 1:
            raise SourceScanError("max_files must be positive")
        if max_bytes < 1:
            raise SourceScanError("max_bytes must be positive")
        if max_ocr_pages < 1:
            raise SourceScanError("max_ocr_pages must be positive")

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
            event_type="scan.started",
            message=f"Started source scan for {source.name}",
            payload={"source_id": source.id, "uri": source.uri},
        )

        scanned_files = 0
        created_documents = 0
        skipped_documents = 0
        segment_count = 0
        for path in iter_supported_files(root):
            if scanned_files >= max_files:
                break
            scanned_files += 1
            text, raw, artifact_kind, extraction_kind = extract_source_text(
                path,
                max_bytes=max_bytes,
                enable_ocr=enable_ocr,
                max_ocr_pages=max_ocr_pages,
            )
            file_hash = content_hash(raw)
            existing = await uow.documents.get_by_domain_and_hash(job.domain_id, file_hash)
            if existing is not None:
                skipped_documents += 1
                continue

            source_uri = path.as_uri()
            relative_path = str(path.relative_to(root if root.is_dir() else root.parent))
            document, version = await uow.documents.add_with_initial_version(
                domain_id=job.domain_id,
                source_id=source.id,
                external_id=relative_path,
                title=path.stem.replace("_", " ").replace("-", " ").strip() or path.name,
                content_hash=file_hash,
                metadata={
                    "ingestion": {
                        "kind": "source_scan",
                        "job_id": job.id,
                        "source_id": source.id,
                        "relative_path": relative_path,
                        "suffix": path.suffix.lower(),
                        "extraction": extraction_kind,
                        "segmenter": "word-window-v1",
                    }
                },
                source_uri=source_uri,
                size_bytes=len(raw),
            )
            await uow.documents.add_artifact(
                document_version_id=version.id,
                kind=artifact_kind,
                uri=source_uri,
                sha256=file_hash,
                size_bytes=len(raw),
            )
            for draft in chunk_text(text, max_tokens=max_segment_tokens):
                await uow.documents.add_segment(
                    document_version_id=version.id,
                    ordinal=draft.ordinal,
                    text=draft.text,
                    anchor=f"{relative_path}#word={draft.anchor.removeprefix('word=')}",
                    token_count=draft.token_count,
                    content_hash=draft.content_hash,
                )
                segment_count += 1
            created_documents += 1
            await uow.journal_events.add(
                actor=actor,
                event_type="document.ingested",
                entity_type="document",
                entity_id=document.id,
                payload={
                    "job_id": job.id,
                    "domain_id": job.domain_id,
                    "source_id": source.id,
                    "version_id": version.id,
                    "content_hash": file_hash,
                    "relative_path": relative_path,
                },
            )

        completed_at = datetime.now(UTC)
        await uow.jobs.update_status(
            job_id=job.id,
            status="succeeded",
            completed_at=completed_at,
        )
        await uow.journal_events.add(
            actor=actor,
            event_type="source.scanned",
            entity_type="source",
            entity_id=source.id,
            payload={
                "job_id": job.id,
                "scanned_files": scanned_files,
                "created_documents": created_documents,
                "skipped_documents": skipped_documents,
                "segment_count": segment_count,
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
            event_type="scan.completed",
            message=f"Scanned {scanned_files} files",
            payload={
                "source_id": source.id,
                "created_documents": created_documents,
                "skipped_documents": skipped_documents,
                "segment_count": segment_count,
            },
        )
        try:
            await uow.commit()
        except IntegrityError as exc:
            raise SourceScanError("Source scan could not be persisted") from exc

    progress_store.append(
        "scan.completed",
        {
            "job_id": job_id,
            "source_id": source.id,
            "created_documents": created_documents,
            "skipped_documents": skipped_documents,
            "segment_count": segment_count,
        },
    )
    return SourceScanResult(
        domain_id=source.domain_id,
        source_id=source.id,
        scanned_files=scanned_files,
        created_documents=created_documents,
        skipped_documents=skipped_documents,
        segment_count=segment_count,
    )


async def fail_source_scan_job(
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
            event_type="scan.failed",
            message="Source scan failed",
            payload={"error": error},
        )
        await uow.commit()

    progress_store.append("scan.failed", {"job_id": job_id, "error": error})
