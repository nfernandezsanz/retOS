from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from retos.domain.documents import Domain, Source, SourceKind
from retos.persistence.models import DomainRecord, SourceRecord


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
