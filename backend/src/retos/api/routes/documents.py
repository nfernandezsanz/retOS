from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from retos.api.dependencies import AdminSubjectDep, UnitOfWorkDep
from retos.api.routes.events import progress_store
from retos.domain.documents import Document, DocumentVersion

router = APIRouter(tags=["documents"])

Hash = Annotated[
    str, Field(min_length=8, max_length=135, pattern=r"^(sha256:)?[a-fA-F0-9]{8,128}$")
]
Title = Annotated[str, Field(min_length=1, max_length=255)]


class DocumentCreate(BaseModel):
    source_id: str | None = Field(default=None, min_length=1, max_length=36)
    external_id: str | None = Field(default=None, max_length=255)
    title: Title
    content_hash: Hash
    source_uri: str = Field(min_length=1, max_length=4000)
    size_bytes: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentRead(BaseModel):
    id: str
    domain_id: str
    source_id: str | None
    external_id: str | None
    title: str
    content_hash: str
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_document(cls, document: Document) -> DocumentRead:
        return cls(
            id=document.id,
            domain_id=document.domain_id,
            source_id=document.source_id,
            external_id=document.external_id,
            title=document.title,
            content_hash=document.content_hash,
            metadata=document.metadata,
            created_at=document.created_at,
            updated_at=document.updated_at,
        )


class DocumentVersionRead(BaseModel):
    id: str
    document_id: str
    version: int
    source_uri: str
    content_hash: str
    size_bytes: int
    created_at: datetime

    @classmethod
    def from_version(cls, version: DocumentVersion) -> DocumentVersionRead:
        return cls(
            id=version.id,
            document_id=version.document_id,
            version=version.version,
            source_uri=version.source_uri,
            content_hash=version.content_hash,
            size_bytes=version.size_bytes,
            created_at=version.created_at,
        )


@router.post(
    "/domains/{domain_id}/documents",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_document(
    payload: DocumentCreate,
    actor: AdminSubjectDep,
    uow: UnitOfWorkDep,
    domain_id: Annotated[str, Path(min_length=1)],
) -> DocumentRead:
    async with uow:
        domain = await uow.domains.get(domain_id)
        if domain is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain not found")
        if payload.source_id is not None:
            source = await uow.sources.get(payload.source_id)
            if source is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Source not found"
                )
            if source.domain_id != domain_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Source does not belong to domain",
                )

        existing = await uow.documents.get_by_domain_and_hash(domain_id, payload.content_hash)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Document content hash already exists for domain",
            )

        document, version = await uow.documents.add_with_initial_version(
            domain_id=domain_id,
            source_id=payload.source_id,
            external_id=payload.external_id,
            title=payload.title,
            content_hash=payload.content_hash,
            metadata=payload.metadata,
            source_uri=payload.source_uri,
            size_bytes=payload.size_bytes,
        )
        await uow.journal_events.add(
            actor=actor,
            event_type="document.created",
            entity_type="document",
            entity_id=document.id,
            payload={
                "domain_id": domain_id,
                "source_id": payload.source_id,
                "version_id": version.id,
                "content_hash": document.content_hash,
            },
        )
        await uow.progress_events.add(
            job_id=None,
            event_type="document.created",
            message=f"Registered document {document.title}",
            payload={"document_id": document.id, "domain_id": domain_id},
        )
        try:
            await uow.commit()
        except IntegrityError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Document content hash already exists for domain",
            ) from exc

    progress_store.append(
        "document.created",
        {"document_id": document.id, "domain_id": domain_id, "title": document.title},
    )
    return DocumentRead.from_document(document)


@router.get("/domains/{domain_id}/documents", response_model=list[DocumentRead])
async def list_documents(
    _: AdminSubjectDep,
    uow: UnitOfWorkDep,
    domain_id: Annotated[str, Path(min_length=1)],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[DocumentRead]:
    async with uow:
        domain = await uow.domains.get(domain_id)
        if domain is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain not found")
        documents = await uow.documents.list_for_domain(domain_id, limit=limit)
    return [DocumentRead.from_document(document) for document in documents]


@router.get("/documents/{document_id}", response_model=DocumentRead)
async def get_document(
    _: AdminSubjectDep,
    uow: UnitOfWorkDep,
    document_id: Annotated[str, Path(min_length=1)],
) -> DocumentRead:
    async with uow:
        document = await uow.documents.get(document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return DocumentRead.from_document(document)


@router.get("/documents/{document_id}/versions", response_model=list[DocumentVersionRead])
async def list_document_versions(
    _: AdminSubjectDep,
    uow: UnitOfWorkDep,
    document_id: Annotated[str, Path(min_length=1)],
) -> list[DocumentVersionRead]:
    async with uow:
        document = await uow.documents.get(document_id)
        if document is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
        versions = await uow.documents.list_versions(document_id)
    return [DocumentVersionRead.from_version(version) for version in versions]
