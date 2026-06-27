from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path, Query, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.exc import IntegrityError

from retos.api.dependencies import AdminSubjectDep, UnitOfWorkDep
from retos.api.routes.events import progress_store
from retos.domain.documents import Artifact, Document, DocumentVersion, Segment

router = APIRouter(tags=["documents"])

Hash = Annotated[
    str, Field(min_length=8, max_length=135, pattern=r"^(sha256:)?[a-fA-F0-9]{8,128}$")
]
Title = Annotated[str, Field(min_length=1, max_length=255)]
ArtifactKind = Annotated[str, Field(min_length=1, max_length=48, pattern=r"^[a-z0-9][a-z0-9._-]*$")]


class DocumentCreate(BaseModel):
    source_id: str | None = Field(default=None, min_length=1, max_length=36)
    external_id: str | None = Field(default=None, max_length=255)
    title: Title
    content_hash: Hash
    source_uri: str = Field(min_length=1, max_length=4000)
    size_bytes: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentUpdate(BaseModel):
    title: Title | None = None
    metadata: dict[str, Any] | None = None

    @model_validator(mode="after")
    def require_update(self) -> DocumentUpdate:
        if self.title is None and self.metadata is None:
            raise ValueError("At least one document field must be provided")
        return self


class DocumentRead(BaseModel):
    id: str
    domain_id: str
    source_id: str | None
    external_id: str | None
    title: str
    content_hash: str
    metadata: dict[str, Any]
    archived_at: datetime | None
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
            archived_at=document.archived_at,
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


class ArtifactCreate(BaseModel):
    kind: ArtifactKind
    uri: str = Field(min_length=1, max_length=4000)
    sha256: Hash
    size_bytes: int = Field(ge=0)


class ArtifactRead(BaseModel):
    id: str
    document_version_id: str
    kind: str
    uri: str
    sha256: str
    size_bytes: int
    created_at: datetime

    @classmethod
    def from_artifact(cls, artifact: Artifact) -> ArtifactRead:
        return cls(
            id=artifact.id,
            document_version_id=artifact.document_version_id,
            kind=artifact.kind,
            uri=artifact.uri,
            sha256=artifact.sha256,
            size_bytes=artifact.size_bytes,
            created_at=artifact.created_at,
        )


class SegmentCreate(BaseModel):
    ordinal: int = Field(ge=0)
    text: str = Field(min_length=1, max_length=100_000)
    anchor: str | None = Field(default=None, max_length=255)
    token_count: int = Field(ge=0)
    content_hash: Hash


class SegmentRead(BaseModel):
    id: str
    document_version_id: str
    ordinal: int
    text: str
    anchor: str | None
    token_count: int
    content_hash: str
    created_at: datetime

    @classmethod
    def from_segment(cls, segment: Segment) -> SegmentRead:
        return cls(
            id=segment.id,
            document_version_id=segment.document_version_id,
            ordinal=segment.ordinal,
            text=segment.text,
            anchor=segment.anchor,
            token_count=segment.token_count,
            content_hash=segment.content_hash,
            created_at=segment.created_at,
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
    include_archived: bool = False,
) -> list[DocumentRead]:
    async with uow:
        domain = await uow.domains.get(domain_id)
        if domain is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain not found")
        documents = await uow.documents.list_for_domain(
            domain_id,
            limit=limit,
            include_archived=include_archived,
        )
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


@router.patch("/documents/{document_id}", response_model=DocumentRead)
async def update_document(
    payload: DocumentUpdate,
    actor: AdminSubjectDep,
    uow: UnitOfWorkDep,
    document_id: Annotated[str, Path(min_length=1)],
) -> DocumentRead:
    async with uow:
        existing = await uow.documents.get(document_id)
        if existing is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
        document = await uow.documents.update(
            document_id,
            title=payload.title,
            metadata=payload.metadata,
        )
        assert document is not None
        await uow.journal_events.add(
            actor=actor,
            event_type="document.updated",
            entity_type="document",
            entity_id=document.id,
            payload={
                "domain_id": document.domain_id,
                "title_changed": payload.title is not None,
                "metadata_changed": payload.metadata is not None,
                "archived": document.archived_at is not None,
            },
        )
        await uow.progress_events.add(
            job_id=None,
            event_type="document.updated",
            message=f"Updated document {document.title}",
            payload={"document_id": document.id, "domain_id": document.domain_id},
        )
        await uow.commit()

    progress_store.append(
        "document.updated",
        {
            "document_id": document.id,
            "domain_id": document.domain_id,
            "title": document.title,
        },
    )
    return DocumentRead.from_document(document)


@router.delete("/documents/{document_id}", response_model=DocumentRead)
async def archive_document(
    actor: AdminSubjectDep,
    uow: UnitOfWorkDep,
    document_id: Annotated[str, Path(min_length=1)],
) -> DocumentRead:
    async with uow:
        existing = await uow.documents.get(document_id)
        if existing is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
        if existing.archived_at is not None:
            return DocumentRead.from_document(existing)
        document = await uow.documents.archive(document_id)
        assert document is not None
        await uow.journal_events.add(
            actor=actor,
            event_type="document.archived",
            entity_type="document",
            entity_id=document.id,
            payload={
                "domain_id": document.domain_id,
                "source_id": document.source_id,
                "content_hash": document.content_hash,
                "archived_at": (
                    document.archived_at.isoformat() if document.archived_at is not None else None
                ),
            },
        )
        await uow.progress_events.add(
            job_id=None,
            event_type="document.archived",
            message=f"Archived document {document.title}",
            payload={"document_id": document.id, "domain_id": document.domain_id},
        )
        await uow.commit()

    progress_store.append(
        "document.archived",
        {
            "document_id": document.id,
            "domain_id": document.domain_id,
            "title": document.title,
        },
    )
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


@router.post(
    "/document-versions/{version_id}/artifacts",
    response_model=ArtifactRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_artifact(
    payload: ArtifactCreate,
    actor: AdminSubjectDep,
    uow: UnitOfWorkDep,
    version_id: Annotated[str, Path(min_length=1)],
) -> ArtifactRead:
    async with uow:
        version = await uow.documents.get_version(version_id)
        if version is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document version not found",
            )
        existing = await uow.documents.get_artifact_by_version_kind_uri(
            document_version_id=version_id,
            kind=payload.kind,
            uri=payload.uri,
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Artifact already exists for document version",
            )
        artifact = await uow.documents.add_artifact(
            document_version_id=version_id,
            kind=payload.kind,
            uri=payload.uri,
            sha256=payload.sha256,
            size_bytes=payload.size_bytes,
        )
        await uow.journal_events.add(
            actor=actor,
            event_type="artifact.created",
            entity_type="artifact",
            entity_id=artifact.id,
            payload={
                "document_id": version.document_id,
                "document_version_id": version_id,
                "kind": artifact.kind,
                "uri": artifact.uri,
            },
        )
        await uow.progress_events.add(
            job_id=None,
            event_type="artifact.created",
            message=f"Registered {artifact.kind} artifact",
            payload={"artifact_id": artifact.id, "document_version_id": version_id},
        )
        try:
            await uow.commit()
        except IntegrityError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Artifact already exists for document version",
            ) from exc

    progress_store.append(
        "artifact.created",
        {"artifact_id": artifact.id, "document_version_id": version_id, "kind": artifact.kind},
    )
    return ArtifactRead.from_artifact(artifact)


@router.get("/document-versions/{version_id}/artifacts", response_model=list[ArtifactRead])
async def list_artifacts(
    _: AdminSubjectDep,
    uow: UnitOfWorkDep,
    version_id: Annotated[str, Path(min_length=1)],
) -> list[ArtifactRead]:
    async with uow:
        version = await uow.documents.get_version(version_id)
        if version is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document version not found",
            )
        artifacts = await uow.documents.list_artifacts(version_id)
    return [ArtifactRead.from_artifact(artifact) for artifact in artifacts]


@router.post(
    "/document-versions/{version_id}/segments",
    response_model=SegmentRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_segment(
    payload: SegmentCreate,
    actor: AdminSubjectDep,
    uow: UnitOfWorkDep,
    version_id: Annotated[str, Path(min_length=1)],
) -> SegmentRead:
    async with uow:
        version = await uow.documents.get_version(version_id)
        if version is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document version not found",
            )
        existing = await uow.documents.get_segment_by_version_ordinal(
            document_version_id=version_id,
            ordinal=payload.ordinal,
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Segment ordinal already exists for document version",
            )
        segment = await uow.documents.add_segment(
            document_version_id=version_id,
            ordinal=payload.ordinal,
            text=payload.text,
            anchor=payload.anchor,
            token_count=payload.token_count,
            content_hash=payload.content_hash,
        )
        await uow.journal_events.add(
            actor=actor,
            event_type="segment.created",
            entity_type="segment",
            entity_id=segment.id,
            payload={
                "document_id": version.document_id,
                "document_version_id": version_id,
                "ordinal": segment.ordinal,
                "content_hash": segment.content_hash,
            },
        )
        await uow.progress_events.add(
            job_id=None,
            event_type="segment.created",
            message=f"Registered segment {segment.ordinal}",
            payload={"segment_id": segment.id, "document_version_id": version_id},
        )
        try:
            await uow.commit()
        except IntegrityError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Segment ordinal already exists for document version",
            ) from exc

    progress_store.append(
        "segment.created",
        {
            "segment_id": segment.id,
            "document_version_id": version_id,
            "ordinal": segment.ordinal,
        },
    )
    return SegmentRead.from_segment(segment)


@router.get("/document-versions/{version_id}/segments", response_model=list[SegmentRead])
async def list_segments(
    _: AdminSubjectDep,
    uow: UnitOfWorkDep,
    version_id: Annotated[str, Path(min_length=1)],
) -> list[SegmentRead]:
    async with uow:
        version = await uow.documents.get_version(version_id)
        if version is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document version not found",
            )
        segments = await uow.documents.list_segments(version_id)
    return [SegmentRead.from_segment(segment) for segment in segments]
