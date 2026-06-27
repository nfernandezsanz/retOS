import builtins
from datetime import datetime
from typing import cast
from uuid import uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from retos.domain.admin import AdminUser
from retos.domain.documents import (
    Artifact,
    Document,
    DocumentVersion,
    Domain,
    Segment,
    Source,
    SourceKind,
    utc_now,
)
from retos.domain.jobs import Job, JobKind, JobStatus, JournalEvent, ProgressEvent
from retos.persistence.models import (
    AdminUserRecord,
    ArtifactRecord,
    DocumentRecord,
    DocumentVersionRecord,
    DomainRecord,
    JobRecord,
    JournalEventRecord,
    ProgressEventRecord,
    SegmentRecord,
    SourceRecord,
)
from retos.search.index import IndexedSegment


def admin_user_from_record(record: AdminUserRecord) -> AdminUser:
    return AdminUser(
        id=record.id,
        email=record.email,
        password_hash=record.password_hash,
        is_active=record.is_active,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def domain_from_record(record: DomainRecord) -> Domain:
    return Domain(
        id=record.id,
        slug=record.slug,
        name=record.name,
        description=record.description,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def source_from_record(record: SourceRecord) -> Source:
    return Source(
        id=record.id,
        domain_id=record.domain_id,
        kind=record.kind,
        name=record.name,
        uri=record.uri,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def document_from_record(record: DocumentRecord) -> Document:
    return Document(
        id=record.id,
        domain_id=record.domain_id,
        source_id=record.source_id,
        external_id=record.external_id,
        title=record.title,
        content_hash=record.content_hash,
        metadata=record.metadata_,
        archived_at=record.archived_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def document_version_from_record(record: DocumentVersionRecord) -> DocumentVersion:
    return DocumentVersion(
        id=record.id,
        document_id=record.document_id,
        version=record.version,
        source_uri=record.source_uri,
        content_hash=record.content_hash,
        size_bytes=record.size_bytes,
        created_at=record.created_at,
    )


def artifact_from_record(record: ArtifactRecord) -> Artifact:
    return Artifact(
        id=record.id,
        document_version_id=record.document_version_id,
        kind=record.kind,
        uri=record.uri,
        sha256=record.sha256,
        size_bytes=record.size_bytes,
        created_at=record.created_at,
    )


def segment_from_record(record: SegmentRecord) -> Segment:
    return Segment(
        id=record.id,
        document_version_id=record.document_version_id,
        ordinal=record.ordinal,
        text=record.text,
        anchor=record.anchor,
        token_count=record.token_count,
        content_hash=record.content_hash,
        created_at=record.created_at,
    )


def job_from_record(record: JobRecord) -> Job:
    return Job(
        id=record.id,
        kind=cast(JobKind, record.kind),
        status=cast(JobStatus, record.status),
        domain_id=record.domain_id,
        source_id=record.source_id,
        payload=record.payload,
        error=record.error,
        started_at=record.started_at,
        completed_at=record.completed_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def journal_event_from_record(record: JournalEventRecord) -> JournalEvent:
    return JournalEvent(
        id=record.id,
        occurred_at=record.occurred_at,
        actor=record.actor,
        event_type=record.event_type,
        entity_type=record.entity_type,
        entity_id=record.entity_id,
        payload=record.payload,
    )


def progress_event_from_record(record: ProgressEventRecord) -> ProgressEvent:
    return ProgressEvent(
        id=record.id,
        job_id=record.job_id,
        occurred_at=record.occurred_at,
        event_type=record.event_type,
        message=record.message,
        payload=record.payload,
    )


class DomainRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, *, slug: str, name: str, description: str | None) -> Domain:
        record = DomainRecord(
            id=str(uuid4()),
            slug=slug,
            name=name,
            description=description,
        )
        self._session.add(record)
        await self._session.flush()
        return domain_from_record(record)

    async def list(self) -> list[Domain]:
        result = await self._session.scalars(select(DomainRecord).order_by(DomainRecord.slug))
        return [domain_from_record(record) for record in result]

    async def get(self, domain_id: str) -> Domain | None:
        record = await self._session.get(DomainRecord, domain_id)
        if record is None:
            return None
        return domain_from_record(record)

    async def get_by_slug(self, slug: str) -> Domain | None:
        result = await self._session.scalars(select(DomainRecord).where(DomainRecord.slug == slug))
        record = result.one_or_none()
        if record is None:
            return None
        return domain_from_record(record)


class AdminUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        email: str,
        password_hash: str,
        is_active: bool = True,
    ) -> AdminUser:
        record = AdminUserRecord(
            id=str(uuid4()),
            email=email,
            password_hash=password_hash,
            is_active=is_active,
        )
        self._session.add(record)
        await self._session.flush()
        return admin_user_from_record(record)

    async def get_by_email(self, email: str) -> AdminUser | None:
        result = await self._session.scalars(
            select(AdminUserRecord).where(AdminUserRecord.email == email)
        )
        record = result.one_or_none()
        if record is None:
            return None
        return admin_user_from_record(record)


class SourceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        domain_id: str,
        kind: SourceKind,
        name: str,
        uri: str,
    ) -> Source:
        record = SourceRecord(
            id=str(uuid4()),
            domain_id=domain_id,
            kind=kind,
            name=name,
            uri=uri,
        )
        self._session.add(record)
        await self._session.flush()
        return source_from_record(record)

    async def list_for_domain(self, domain_id: str) -> list[Source]:
        result = await self._session.scalars(
            select(SourceRecord)
            .where(SourceRecord.domain_id == domain_id)
            .order_by(SourceRecord.created_at, SourceRecord.id)
        )
        return [source_from_record(record) for record in result]

    async def get_by_domain_and_uri(self, domain_id: str, uri: str) -> Source | None:
        result = await self._session.scalars(
            select(SourceRecord).where(
                SourceRecord.domain_id == domain_id,
                SourceRecord.uri == uri,
            )
        )
        record = result.one_or_none()
        if record is None:
            return None
        return source_from_record(record)

    async def get(self, source_id: str) -> Source | None:
        record = await self._session.get(SourceRecord, source_id)
        if record is None:
            return None
        return source_from_record(record)


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_with_initial_version(
        self,
        *,
        domain_id: str,
        source_id: str | None,
        external_id: str | None,
        title: str,
        content_hash: str,
        metadata: dict[str, object],
        source_uri: str,
        size_bytes: int,
    ) -> tuple[Document, DocumentVersion]:
        document_record = DocumentRecord(
            id=str(uuid4()),
            domain_id=domain_id,
            source_id=source_id,
            external_id=external_id,
            title=title,
            content_hash=content_hash,
            metadata_=metadata,
        )
        self._session.add(document_record)
        await self._session.flush()

        version_record = DocumentVersionRecord(
            id=str(uuid4()),
            document_id=document_record.id,
            version=1,
            source_uri=source_uri,
            content_hash=content_hash,
            size_bytes=size_bytes,
        )
        self._session.add(version_record)
        await self._session.flush()
        return document_from_record(document_record), document_version_from_record(version_record)

    async def get(self, document_id: str) -> Document | None:
        record = await self._session.get(DocumentRecord, document_id)
        if record is None:
            return None
        return document_from_record(record)

    async def get_by_domain_and_hash(self, domain_id: str, content_hash: str) -> Document | None:
        result = await self._session.scalars(
            select(DocumentRecord).where(
                DocumentRecord.domain_id == domain_id,
                DocumentRecord.content_hash == content_hash,
            )
        )
        record = result.one_or_none()
        if record is None:
            return None
        return document_from_record(record)

    async def list_for_domain(
        self,
        domain_id: str,
        *,
        limit: int = 100,
        include_archived: bool = False,
    ) -> list[Document]:
        statement = select(DocumentRecord).where(DocumentRecord.domain_id == domain_id)
        if not include_archived:
            statement = statement.where(DocumentRecord.archived_at.is_(None))
        result = await self._session.scalars(
            statement.order_by(DocumentRecord.created_at.desc(), DocumentRecord.id.desc()).limit(
                limit
            )
        )
        return [document_from_record(record) for record in result]

    async def update(
        self,
        document_id: str,
        *,
        title: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> Document | None:
        record = await self._session.get(DocumentRecord, document_id)
        if record is None:
            return None
        if title is not None:
            record.title = title
        if metadata is not None:
            record.metadata_ = metadata
        record.updated_at = utc_now()
        await self._session.flush()
        return document_from_record(record)

    async def archive(self, document_id: str) -> Document | None:
        record = await self._session.get(DocumentRecord, document_id)
        if record is None:
            return None
        if record.archived_at is None:
            now = utc_now()
            record.archived_at = now
            record.updated_at = now
            await self._session.flush()
        return document_from_record(record)

    async def restore(self, document_id: str) -> Document | None:
        record = await self._session.get(DocumentRecord, document_id)
        if record is None:
            return None
        if record.archived_at is not None:
            record.archived_at = None
            record.updated_at = utc_now()
            await self._session.flush()
        return document_from_record(record)

    async def list_versions(self, document_id: str) -> list[DocumentVersion]:
        result = await self._session.scalars(
            select(DocumentVersionRecord)
            .where(DocumentVersionRecord.document_id == document_id)
            .order_by(DocumentVersionRecord.version)
        )
        return [document_version_from_record(record) for record in result]

    async def get_version(self, version_id: str) -> DocumentVersion | None:
        record = await self._session.get(DocumentVersionRecord, version_id)
        if record is None:
            return None
        return document_version_from_record(record)

    async def add_artifact(
        self,
        *,
        document_version_id: str,
        kind: str,
        uri: str,
        sha256: str,
        size_bytes: int,
    ) -> Artifact:
        record = ArtifactRecord(
            id=str(uuid4()),
            document_version_id=document_version_id,
            kind=kind,
            uri=uri,
            sha256=sha256,
            size_bytes=size_bytes,
        )
        self._session.add(record)
        await self._session.flush()
        return artifact_from_record(record)

    async def get_artifact_by_version_kind_uri(
        self,
        *,
        document_version_id: str,
        kind: str,
        uri: str,
    ) -> Artifact | None:
        result = await self._session.scalars(
            select(ArtifactRecord).where(
                ArtifactRecord.document_version_id == document_version_id,
                ArtifactRecord.kind == kind,
                ArtifactRecord.uri == uri,
            )
        )
        record = result.one_or_none()
        if record is None:
            return None
        return artifact_from_record(record)

    async def list_artifacts(self, document_version_id: str) -> list[Artifact]:
        result = await self._session.scalars(
            select(ArtifactRecord)
            .where(ArtifactRecord.document_version_id == document_version_id)
            .order_by(ArtifactRecord.kind, ArtifactRecord.created_at, ArtifactRecord.id)
        )
        return [artifact_from_record(record) for record in result]

    async def add_segment(
        self,
        *,
        document_version_id: str,
        ordinal: int,
        text: str,
        anchor: str | None,
        token_count: int,
        content_hash: str,
    ) -> Segment:
        record = SegmentRecord(
            id=str(uuid4()),
            document_version_id=document_version_id,
            ordinal=ordinal,
            text=text,
            anchor=anchor,
            token_count=token_count,
            content_hash=content_hash,
        )
        self._session.add(record)
        await self._session.flush()
        return segment_from_record(record)

    async def get_segment_by_version_ordinal(
        self,
        *,
        document_version_id: str,
        ordinal: int,
    ) -> Segment | None:
        result = await self._session.scalars(
            select(SegmentRecord).where(
                SegmentRecord.document_version_id == document_version_id,
                SegmentRecord.ordinal == ordinal,
            )
        )
        record = result.one_or_none()
        if record is None:
            return None
        return segment_from_record(record)

    async def list_segments(self, document_version_id: str) -> list[Segment]:
        result = await self._session.scalars(
            select(SegmentRecord)
            .where(SegmentRecord.document_version_id == document_version_id)
            .order_by(SegmentRecord.ordinal)
        )
        return [segment_from_record(record) for record in result]

    async def list_indexable_segments(self, domain_id: str) -> list[IndexedSegment]:
        result = await self._session.execute(
            select(
                SegmentRecord.id,
                SegmentRecord.document_version_id,
                SegmentRecord.ordinal,
                SegmentRecord.text,
                SegmentRecord.anchor,
                DocumentRecord.id,
                DocumentRecord.title,
            )
            .join(
                DocumentVersionRecord,
                SegmentRecord.document_version_id == DocumentVersionRecord.id,
            )
            .join(DocumentRecord, DocumentVersionRecord.document_id == DocumentRecord.id)
            .where(
                DocumentRecord.domain_id == domain_id,
                DocumentRecord.archived_at.is_(None),
            )
            .order_by(DocumentRecord.created_at, DocumentRecord.id, SegmentRecord.ordinal)
        )
        return [
            IndexedSegment(
                segment_id=row[0],
                document_version_id=row[1],
                ordinal=row[2],
                text=row[3],
                anchor=row[4],
                document_id=row[5],
                title=row[6],
            )
            for row in result.all()
        ]


class JobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        kind: JobKind,
        status: JobStatus,
        domain_id: str | None,
        source_id: str | None,
        payload: dict[str, object],
    ) -> Job:
        record = JobRecord(
            id=str(uuid4()),
            kind=kind,
            status=status,
            domain_id=domain_id,
            source_id=source_id,
            payload=payload,
        )
        self._session.add(record)
        await self._session.flush()
        return job_from_record(record)

    async def get(self, job_id: str) -> Job | None:
        record = await self._session.get(JobRecord, job_id)
        if record is None:
            return None
        return job_from_record(record)

    async def update_status(
        self,
        *,
        job_id: str,
        status: JobStatus,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        error: str | None = None,
    ) -> Job | None:
        record = await self._session.get(JobRecord, job_id)
        if record is None:
            return None
        record.status = status
        record.error = error
        if started_at is not None:
            record.started_at = started_at
        if completed_at is not None:
            record.completed_at = completed_at
        await self._session.flush()
        return job_from_record(record)

    async def update_payload(self, *, job_id: str, payload: dict[str, object]) -> Job | None:
        record = await self._session.get(JobRecord, job_id)
        if record is None:
            return None
        record.payload = payload
        await self._session.flush()
        return job_from_record(record)

    async def list(self, *, limit: int = 100) -> list[Job]:
        result = await self._session.scalars(
            select(JobRecord)
            .order_by(JobRecord.created_at.desc(), JobRecord.id.desc())
            .limit(limit)
        )
        return [job_from_record(record) for record in result]

    async def list_by_kind(self, *, kind: JobKind, limit: int = 100) -> builtins.list[Job]:
        result = await self._session.scalars(
            select(JobRecord)
            .where(JobRecord.kind == kind)
            .order_by(JobRecord.created_at.desc(), JobRecord.id.desc())
            .limit(limit)
        )
        return [job_from_record(record) for record in result]


class JournalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        actor: str,
        event_type: str,
        entity_type: str,
        entity_id: str,
        payload: dict[str, object],
    ) -> JournalEvent:
        record = JournalEventRecord(
            id=str(uuid4()),
            actor=actor,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload,
        )
        self._session.add(record)
        await self._session.flush()
        return journal_event_from_record(record)

    async def list(self, *, limit: int = 100) -> list[JournalEvent]:
        result = await self._session.scalars(
            select(JournalEventRecord)
            .order_by(JournalEventRecord.occurred_at.desc(), JournalEventRecord.id.desc())
            .limit(limit)
        )
        return [journal_event_from_record(record) for record in result]


class ProgressEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        job_id: str | None,
        event_type: str,
        message: str,
        payload: dict[str, object],
    ) -> ProgressEvent:
        record = ProgressEventRecord(
            id=str(uuid4()),
            job_id=job_id,
            event_type=event_type,
            message=message,
            payload=payload,
        )
        self._session.add(record)
        await self._session.flush()
        return progress_event_from_record(record)

    async def list(self, *, limit: int = 100) -> list[ProgressEvent]:
        result = await self._session.scalars(
            select(ProgressEventRecord)
            .order_by(ProgressEventRecord.occurred_at.desc(), ProgressEventRecord.id.desc())
            .limit(limit)
        )
        return [progress_event_from_record(record) for record in result]

    async def list_chronological(self, *, limit: int = 100) -> builtins.list[ProgressEvent]:
        result = await self._session.scalars(
            select(ProgressEventRecord)
            .order_by(ProgressEventRecord.occurred_at.desc(), ProgressEventRecord.id.desc())
            .limit(limit)
        )
        return [progress_event_from_record(record) for record in reversed(result.all())]

    async def list_after(
        self,
        *,
        event_id: str,
        limit: int = 100,
    ) -> builtins.list[ProgressEvent]:
        target = await self._session.get(ProgressEventRecord, event_id)
        if target is None:
            return await self.list_chronological(limit=limit)
        result = await self._session.scalars(
            select(ProgressEventRecord)
            .where(
                or_(
                    ProgressEventRecord.occurred_at > target.occurred_at,
                    and_(
                        ProgressEventRecord.occurred_at == target.occurred_at,
                        ProgressEventRecord.id > target.id,
                    ),
                )
            )
            .order_by(ProgressEventRecord.occurred_at.asc(), ProgressEventRecord.id.asc())
            .limit(limit)
        )
        return [progress_event_from_record(record) for record in result]
