from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from retos.api.dependencies import (
    AdminSubjectDep,
    UnitOfWorkDep,
    ViewerSubjectDep,
    ensure_domain_access,
)
from retos.domain.documents import Domain, Source, SourceKind

router = APIRouter(prefix="/domains", tags=["domains"])

Slug = Annotated[str, Field(min_length=2, max_length=80, pattern=r"^[a-z0-9][a-z0-9-]*$")]
Name = Annotated[str, Field(min_length=1, max_length=160)]


class DomainCreate(BaseModel):
    slug: Slug
    name: Name
    description: str | None = Field(default=None, max_length=2000)


class DomainUpdate(BaseModel):
    name: Name
    description: str | None = Field(default=None, max_length=2000)


class DomainRead(BaseModel):
    id: str
    slug: str
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_domain(cls, domain: Domain) -> DomainRead:
        return cls(
            id=domain.id,
            slug=domain.slug,
            name=domain.name,
            description=domain.description,
            created_at=domain.created_at,
            updated_at=domain.updated_at,
        )


class SourceCreate(BaseModel):
    kind: SourceKind = "upload"
    name: Name
    uri: str = Field(min_length=1, max_length=4000)


class SourceUpdate(BaseModel):
    kind: SourceKind
    name: Name
    uri: str = Field(min_length=1, max_length=4000)


class SourceRead(BaseModel):
    id: str
    domain_id: str
    kind: SourceKind
    name: str
    uri: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_source(cls, source: Source) -> SourceRead:
        return cls(
            id=source.id,
            domain_id=source.domain_id,
            kind=source.kind,
            name=source.name,
            uri=source.uri,
            created_at=source.created_at,
            updated_at=source.updated_at,
        )


@router.post("", response_model=DomainRead, status_code=status.HTTP_201_CREATED)
async def create_domain(
    payload: DomainCreate,
    _: AdminSubjectDep,
    uow: UnitOfWorkDep,
) -> DomainRead:
    async with uow:
        existing = await uow.domains.get_by_slug(payload.slug)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Domain slug already exists",
            )
        domain = await uow.domains.add(
            slug=payload.slug,
            name=payload.name,
            description=payload.description,
        )
        try:
            await uow.commit()
        except IntegrityError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Domain slug already exists",
            ) from exc
        return DomainRead.from_domain(domain)


@router.get("", response_model=list[DomainRead])
async def list_domains(actor: ViewerSubjectDep, uow: UnitOfWorkDep) -> list[DomainRead]:
    async with uow:
        admin = await uow.admin_users.get_by_email(actor)
        if admin is not None and "admin" in admin.roles:
            domains = await uow.domains.list()
        elif admin is not None:
            domains = await uow.domains.list_for_admin_user(admin.id)
        else:
            domains = []
    return [DomainRead.from_domain(domain) for domain in domains]


@router.get("/{domain_id}", response_model=DomainRead)
async def get_domain(
    actor: ViewerSubjectDep,
    uow: UnitOfWorkDep,
    domain_id: Annotated[str, Path(min_length=1)],
) -> DomainRead:
    async with uow:
        domain = await uow.domains.get(domain_id)
        if domain is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain not found")
        await ensure_domain_access(actor=actor, domain_id=domain_id, uow=uow)
    return DomainRead.from_domain(domain)


@router.patch("/{domain_id}", response_model=DomainRead)
async def update_domain(
    payload: DomainUpdate,
    actor: AdminSubjectDep,
    uow: UnitOfWorkDep,
    domain_id: Annotated[str, Path(min_length=1)],
) -> DomainRead:
    async with uow:
        existing = await uow.domains.get(domain_id)
        if existing is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain not found")
        domain = await uow.domains.update_details(
            domain_id=domain_id,
            name=payload.name,
            description=payload.description,
        )
        assert domain is not None
        await uow.journal_events.add(
            actor=actor,
            event_type="domain.updated",
            entity_type="domain",
            entity_id=domain.id,
            payload={
                "domain_id": domain.id,
                "slug": domain.slug,
                "changes": [
                    {
                        "field": "name",
                        "before": existing.name,
                        "after": domain.name,
                    },
                    {
                        "field": "description",
                        "before": existing.description,
                        "after": domain.description,
                    },
                ],
            },
        )
        await uow.commit()
    return DomainRead.from_domain(domain)


@router.post(
    "/{domain_id}/sources",
    response_model=SourceRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_source(
    payload: SourceCreate,
    _: AdminSubjectDep,
    uow: UnitOfWorkDep,
    domain_id: Annotated[str, Path(min_length=1)],
) -> SourceRead:
    async with uow:
        domain = await uow.domains.get(domain_id)
        if domain is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain not found")
        existing = await uow.sources.get_by_domain_and_uri(domain_id, payload.uri)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Source URI already exists for domain",
            )
        source = await uow.sources.add(
            domain_id=domain_id,
            kind=payload.kind,
            name=payload.name,
            uri=payload.uri,
        )
        try:
            await uow.commit()
        except IntegrityError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Source URI already exists for domain",
            ) from exc
        return SourceRead.from_source(source)


@router.get("/{domain_id}/sources", response_model=list[SourceRead])
async def list_sources(
    actor: ViewerSubjectDep,
    uow: UnitOfWorkDep,
    domain_id: Annotated[str, Path(min_length=1)],
) -> list[SourceRead]:
    async with uow:
        domain = await uow.domains.get(domain_id)
        if domain is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain not found")
        await ensure_domain_access(actor=actor, domain_id=domain_id, uow=uow)
        sources = await uow.sources.list_for_domain(domain_id)
    return [SourceRead.from_source(source) for source in sources]


@router.patch("/{domain_id}/sources/{source_id}", response_model=SourceRead)
async def update_source(
    payload: SourceUpdate,
    actor: AdminSubjectDep,
    uow: UnitOfWorkDep,
    domain_id: Annotated[str, Path(min_length=1)],
    source_id: Annotated[str, Path(min_length=1)],
) -> SourceRead:
    async with uow:
        domain = await uow.domains.get(domain_id)
        if domain is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain not found")
        existing = await uow.sources.get(source_id)
        if existing is None or existing.domain_id != domain_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
        duplicate = await uow.sources.get_by_domain_and_uri(domain_id, payload.uri)
        if duplicate is not None and duplicate.id != source_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Source URI already exists for domain",
            )
        source = await uow.sources.update_details(
            source_id=source_id,
            kind=payload.kind,
            name=payload.name,
            uri=payload.uri,
        )
        assert source is not None
        await uow.journal_events.add(
            actor=actor,
            event_type="source.updated",
            entity_type="source",
            entity_id=source.id,
            payload={
                "domain_id": domain_id,
                "source_id": source.id,
                "changes": [
                    {
                        "field": "kind",
                        "before": existing.kind,
                        "after": source.kind,
                    },
                    {
                        "field": "name",
                        "before": existing.name,
                        "after": source.name,
                    },
                    {
                        "field": "uri",
                        "before": existing.uri,
                        "after": source.uri,
                    },
                ],
            },
        )
        try:
            await uow.commit()
        except IntegrityError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Source URI already exists for domain",
            ) from exc
    return SourceRead.from_source(source)


@router.delete("/{domain_id}/sources/{source_id}", response_model=SourceRead)
async def delete_source(
    actor: AdminSubjectDep,
    uow: UnitOfWorkDep,
    domain_id: Annotated[str, Path(min_length=1)],
    source_id: Annotated[str, Path(min_length=1)],
) -> SourceRead:
    async with uow:
        domain = await uow.domains.get(domain_id)
        if domain is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain not found")
        existing = await uow.sources.get(source_id)
        if existing is None or existing.domain_id != domain_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
        source = await uow.sources.delete(source_id)
        assert source is not None
        await uow.journal_events.add(
            actor=actor,
            event_type="source.deleted",
            entity_type="source",
            entity_id=source.id,
            payload={
                "domain_id": domain_id,
                "source_id": source.id,
                "kind": existing.kind,
                "name": existing.name,
                "uri": existing.uri,
            },
        )
        await uow.commit()
    return SourceRead.from_source(source)
