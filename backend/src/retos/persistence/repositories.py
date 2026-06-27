from typing import cast
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from retos.domain.documents import Domain, Source, SourceKind
from retos.domain.jobs import Job, JobKind, JobStatus, JournalEvent, ProgressEvent
from retos.persistence.models import (
    DomainRecord,
    JobRecord,
    JournalEventRecord,
    ProgressEventRecord,
    SourceRecord,
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

    async def list(self, *, limit: int = 100) -> list[Job]:
        result = await self._session.scalars(
            select(JobRecord)
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
