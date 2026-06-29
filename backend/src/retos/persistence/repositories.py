import builtins
from datetime import datetime
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from retos.core.audit_hash import audit_event_hash, audit_payload_hash
from retos.domain.admin import AdminUser, AdminUserDomainGrant, normalize_admin_roles
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
    AdminUserDomainGrantRecord,
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
        roles=normalize_admin_roles(record.roles or ["admin"]),
        is_active=record.is_active,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def admin_user_domain_grant_from_record(
    record: AdminUserDomainGrantRecord,
) -> AdminUserDomainGrant:
    return AdminUserDomainGrant(
        id=record.id,
        admin_user_id=record.admin_user_id,
        domain_id=record.domain_id,
        created_at=record.created_at,
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
        trace_id=record.trace_id,
        payload_hash=record.payload_hash,
        prev_hash=record.prev_hash,
        event_hash=record.event_hash,
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
        trace_id=record.trace_id,
        payload_hash=record.payload_hash,
        prev_hash=record.prev_hash,
        event_hash=record.event_hash,
        job_id=record.job_id,
        occurred_at=record.occurred_at,
        event_type=record.event_type,
        message=record.message,
        payload=record.payload,
    )


def payload_domain_id(payload: dict[str, Any]) -> str | None:
    value = payload.get("domain_id")
    return value if isinstance(value, str) and value else None


def payload_trace_id(payload: dict[str, object]) -> str | None:
    value = payload.get("trace_id")
    return value if isinstance(value, str) and value else None


def journal_trace_id(
    *,
    entity_type: str,
    entity_id: str,
    payload: dict[str, object],
) -> str | None:
    return payload_trace_id(payload) or (entity_id if entity_type == "job" else None)


def progress_trace_id(*, job_id: str | None, payload: dict[str, object]) -> str | None:
    return payload_trace_id(payload) or job_id


async def latest_audit_event_hash(session: AsyncSession) -> str | None:
    journal_result = await session.execute(
        select(
            JournalEventRecord.occurred_at,
            JournalEventRecord.id,
            JournalEventRecord.event_hash,
        )
        .where(JournalEventRecord.event_hash.is_not(None))
        .order_by(JournalEventRecord.occurred_at.desc(), JournalEventRecord.id.desc())
        .limit(1)
    )
    progress_result = await session.execute(
        select(
            ProgressEventRecord.occurred_at,
            ProgressEventRecord.id,
            ProgressEventRecord.event_hash,
        )
        .where(ProgressEventRecord.event_hash.is_not(None))
        .order_by(ProgressEventRecord.occurred_at.desc(), ProgressEventRecord.id.desc())
        .limit(1)
    )
    candidates = [
        row
        for row in (journal_result.first(), progress_result.first())
        if row is not None and row.event_hash is not None
    ]
    if not candidates:
        return None
    latest = max(candidates, key=lambda row: (row.occurred_at, row.id))
    return cast(str, latest.event_hash)


def journal_record_visible_to_domains(
    record: JournalEventRecord,
    domain_ids: set[str],
    job_domains: dict[str, str | None],
) -> bool:
    if record.entity_type == "domain" and record.entity_id in domain_ids:
        return True
    domain_id = payload_domain_id(record.payload)
    if domain_id in domain_ids:
        return True
    return record.entity_type == "job" and job_domains.get(record.entity_id) in domain_ids


def progress_record_visible_to_domains(
    record: ProgressEventRecord,
    domain_ids: set[str],
    job_domains: dict[str, str | None],
) -> bool:
    domain_id = payload_domain_id(record.payload)
    if domain_id in domain_ids:
        return True
    return record.job_id is not None and job_domains.get(record.job_id) in domain_ids


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

    async def list_for_admin_user(self, admin_user_id: str) -> builtins.list[Domain]:
        result = await self._session.scalars(
            select(DomainRecord)
            .join(
                AdminUserDomainGrantRecord,
                AdminUserDomainGrantRecord.domain_id == DomainRecord.id,
            )
            .where(AdminUserDomainGrantRecord.admin_user_id == admin_user_id)
            .order_by(DomainRecord.slug)
        )
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

    async def update_details(
        self,
        *,
        domain_id: str,
        name: str,
        description: str | None,
    ) -> Domain | None:
        record = await self._session.get(DomainRecord, domain_id)
        if record is None:
            return None
        record.name = name
        record.description = description
        await self._session.flush()
        return domain_from_record(record)


class AdminUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        email: str,
        password_hash: str,
        roles: tuple[str, ...] = ("admin",),
        is_active: bool = True,
    ) -> AdminUser:
        record = AdminUserRecord(
            id=str(uuid4()),
            email=email,
            password_hash=password_hash,
            roles=list(normalize_admin_roles(roles)),
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

    async def get(self, admin_user_id: str) -> AdminUser | None:
        record = await self._session.get(AdminUserRecord, admin_user_id)
        if record is None:
            return None
        return admin_user_from_record(record)

    async def list(self, *, limit: int = 100) -> builtins.list[AdminUser]:
        result = await self._session.scalars(
            select(AdminUserRecord)
            .order_by(AdminUserRecord.created_at.asc(), AdminUserRecord.email.asc())
            .limit(limit)
        )
        return [admin_user_from_record(record) for record in result]

    async def count_active(self) -> int:
        result = await self._session.scalar(
            select(func.count()).select_from(AdminUserRecord).where(AdminUserRecord.is_active)
        )
        return int(result or 0)

    async def count_active_admins(self) -> int:
        result = await self._session.scalars(
            select(AdminUserRecord).where(AdminUserRecord.is_active)
        )
        return sum(1 for record in result if "admin" in normalize_admin_roles(record.roles))

    async def update_active(self, *, admin_user_id: str, is_active: bool) -> AdminUser | None:
        record = await self._session.get(AdminUserRecord, admin_user_id)
        if record is None:
            return None
        record.is_active = is_active
        await self._session.flush()
        return admin_user_from_record(record)

    async def update_roles(self, *, admin_user_id: str, roles: tuple[str, ...]) -> AdminUser | None:
        record = await self._session.get(AdminUserRecord, admin_user_id)
        if record is None:
            return None
        record.roles = list(normalize_admin_roles(roles))
        await self._session.flush()
        return admin_user_from_record(record)

    async def update_password(self, *, admin_user_id: str, password_hash: str) -> AdminUser | None:
        record = await self._session.get(AdminUserRecord, admin_user_id)
        if record is None:
            return None
        record.password_hash = password_hash
        await self._session.flush()
        return admin_user_from_record(record)

    async def add_domain_grant(
        self,
        *,
        admin_user_id: str,
        domain_id: str,
    ) -> AdminUserDomainGrant:
        record = AdminUserDomainGrantRecord(
            id=str(uuid4()),
            admin_user_id=admin_user_id,
            domain_id=domain_id,
        )
        self._session.add(record)
        await self._session.flush()
        return admin_user_domain_grant_from_record(record)

    async def get_domain_grant(
        self,
        *,
        admin_user_id: str,
        domain_id: str,
    ) -> AdminUserDomainGrant | None:
        result = await self._session.scalars(
            select(AdminUserDomainGrantRecord).where(
                AdminUserDomainGrantRecord.admin_user_id == admin_user_id,
                AdminUserDomainGrantRecord.domain_id == domain_id,
            )
        )
        record = result.one_or_none()
        if record is None:
            return None
        return admin_user_domain_grant_from_record(record)

    async def list_domain_grants(self, admin_user_id: str) -> builtins.list[AdminUserDomainGrant]:
        result = await self._session.scalars(
            select(AdminUserDomainGrantRecord)
            .where(AdminUserDomainGrantRecord.admin_user_id == admin_user_id)
            .order_by(AdminUserDomainGrantRecord.created_at, AdminUserDomainGrantRecord.id)
        )
        return [admin_user_domain_grant_from_record(record) for record in result]

    async def remove_domain_grant(self, *, admin_user_id: str, domain_id: str) -> bool:
        result = await self._session.scalars(
            select(AdminUserDomainGrantRecord).where(
                AdminUserDomainGrantRecord.admin_user_id == admin_user_id,
                AdminUserDomainGrantRecord.domain_id == domain_id,
            )
        )
        record = result.one_or_none()
        if record is None:
            return False
        await self._session.delete(record)
        await self._session.flush()
        return True

    async def can_access_domain(self, *, email: str, domain_id: str) -> bool:
        admin = await self.get_by_email(email)
        if admin is None or not admin.is_active:
            return False
        if "admin" in admin.roles:
            return True
        grant = await self.get_domain_grant(admin_user_id=admin.id, domain_id=domain_id)
        return grant is not None


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

    async def update_details(
        self,
        *,
        source_id: str,
        kind: SourceKind,
        name: str,
        uri: str,
    ) -> Source | None:
        record = await self._session.get(SourceRecord, source_id)
        if record is None:
            return None
        record.kind = kind
        record.name = name
        record.uri = uri
        await self._session.flush()
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

    async def list_for_admin_user(
        self,
        *,
        admin_user_id: str,
        limit: int = 100,
    ) -> builtins.list[Job]:
        result = await self._session.scalars(
            select(JobRecord)
            .join(
                AdminUserDomainGrantRecord,
                AdminUserDomainGrantRecord.domain_id == JobRecord.domain_id,
            )
            .where(AdminUserDomainGrantRecord.admin_user_id == admin_user_id)
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
        event_id = str(uuid4())
        occurred_at = utc_now()
        trace_id = journal_trace_id(
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload,
        )
        payload_hash = audit_payload_hash(payload)
        prev_hash = await latest_audit_event_hash(self._session)
        record = JournalEventRecord(
            id=event_id,
            trace_id=trace_id,
            payload_hash=payload_hash,
            prev_hash=prev_hash,
            event_hash=audit_event_hash(
                event_id=event_id,
                trace_id=trace_id,
                event_stream="journal",
                event_type=event_type,
                occurred_at=occurred_at,
                payload_hash=payload_hash,
                prev_hash=prev_hash,
            ),
            occurred_at=occurred_at,
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

    async def list_for_domain_ids(
        self,
        *,
        domain_ids: set[str],
        limit: int = 100,
    ) -> builtins.list[JournalEvent]:
        if not domain_ids:
            return []
        window = min(max(limit * 20, limit), 1000)
        result = await self._session.scalars(
            select(JournalEventRecord)
            .order_by(JournalEventRecord.occurred_at.desc(), JournalEventRecord.id.desc())
            .limit(window)
        )
        records = result.all()
        job_ids = [
            record.entity_id
            for record in records
            if record.entity_type == "job" and record.entity_id
        ]
        job_domains: dict[str, str | None] = {}
        if job_ids:
            job_result = await self._session.scalars(
                select(JobRecord).where(JobRecord.id.in_(job_ids))
            )
            job_domains = {record.id: record.domain_id for record in job_result}
        visible = [
            journal_event_from_record(record)
            for record in records
            if journal_record_visible_to_domains(record, domain_ids, job_domains)
        ]
        return visible[:limit]

    async def list_for_entity(
        self,
        *,
        entity_type: str,
        entity_id: str,
        limit: int = 100,
    ) -> builtins.list[JournalEvent]:
        result = await self._session.scalars(
            select(JournalEventRecord)
            .where(
                JournalEventRecord.entity_type == entity_type,
                JournalEventRecord.entity_id == entity_id,
            )
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
        event_id = str(uuid4())
        occurred_at = utc_now()
        trace_id = progress_trace_id(job_id=job_id, payload=payload)
        payload_hash = audit_payload_hash(payload)
        prev_hash = await latest_audit_event_hash(self._session)
        record = ProgressEventRecord(
            id=event_id,
            trace_id=trace_id,
            payload_hash=payload_hash,
            prev_hash=prev_hash,
            event_hash=audit_event_hash(
                event_id=event_id,
                trace_id=trace_id,
                event_stream="progress",
                event_type=event_type,
                occurred_at=occurred_at,
                payload_hash=payload_hash,
                prev_hash=prev_hash,
            ),
            occurred_at=occurred_at,
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

    async def list_for_domain_ids(
        self,
        *,
        domain_ids: set[str],
        limit: int = 100,
    ) -> builtins.list[ProgressEvent]:
        if not domain_ids:
            return []
        window = min(max(limit * 20, limit), 1000)
        result = await self._session.scalars(
            select(ProgressEventRecord)
            .order_by(ProgressEventRecord.occurred_at.desc(), ProgressEventRecord.id.desc())
            .limit(window)
        )
        records = result.all()
        job_ids = [record.job_id for record in records if record.job_id is not None]
        job_domains: dict[str, str | None] = {}
        if job_ids:
            job_result = await self._session.scalars(
                select(JobRecord).where(JobRecord.id.in_(job_ids))
            )
            job_domains = {record.id: record.domain_id for record in job_result}
        visible = [
            progress_event_from_record(record)
            for record in records
            if progress_record_visible_to_domains(record, domain_ids, job_domains)
        ]
        return visible[:limit]

    async def list_chronological_for_domain_ids(
        self,
        *,
        domain_ids: set[str],
        limit: int = 100,
    ) -> builtins.list[ProgressEvent]:
        visible = await self.list_for_domain_ids(domain_ids=domain_ids, limit=limit)
        return builtins.list(reversed(visible))

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

    async def list_after_for_domain_ids(
        self,
        *,
        event_id: str,
        domain_ids: set[str],
        limit: int = 100,
    ) -> builtins.list[ProgressEvent]:
        if not domain_ids:
            return []
        target = await self._session.get(ProgressEventRecord, event_id)
        if target is None:
            return await self.list_chronological_for_domain_ids(
                domain_ids=domain_ids,
                limit=limit,
            )
        window = min(max(limit * 20, limit), 1000)
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
            .limit(window)
        )
        records = result.all()
        job_ids = [record.job_id for record in records if record.job_id is not None]
        job_domains: dict[str, str | None] = {}
        if job_ids:
            job_result = await self._session.scalars(
                select(JobRecord).where(JobRecord.id.in_(job_ids))
            )
            job_domains = {record.id: record.domain_id for record in job_result}
        visible = [
            progress_event_from_record(record)
            for record in records
            if progress_record_visible_to_domains(record, domain_ids, job_domains)
        ]
        return visible[:limit]
