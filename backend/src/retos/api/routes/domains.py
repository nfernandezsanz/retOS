from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from retos.api.dependencies import AdminSubjectDep, UnitOfWorkDep
from retos.domain.documents import Domain, Source, SourceKind

router = APIRouter(prefix="/domains", tags=["domains"])

Slug = Annotated[str, Field(min_length=2, max_length=80, pattern=r"^[a-z0-9][a-z0-9-]*$")]
Name = Annotated[str, Field(min_length=1, max_length=160)]


class DomainCreate(BaseModel):
    slug: Slug
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
async def list_domains(_: AdminSubjectDep, uow: UnitOfWorkDep) -> list[DomainRead]:
    async with uow:
        domains = await uow.domains.list()
    return [DomainRead.from_domain(domain) for domain in domains]


@router.get("/{domain_id}", response_model=DomainRead)
async def get_domain(
    _: AdminSubjectDep,
    uow: UnitOfWorkDep,
    domain_id: Annotated[str, Path(min_length=1)],
) -> DomainRead:
    async with uow:
        domain = await uow.domains.get(domain_id)
    if domain is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain not found")
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
    _: AdminSubjectDep,
    uow: UnitOfWorkDep,
    domain_id: Annotated[str, Path(min_length=1)],
) -> list[SourceRead]:
    async with uow:
        domain = await uow.domains.get(domain_id)
        if domain is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain not found")
        sources = await uow.sources.list_for_domain(domain_id)
    return [SourceRead.from_source(source) for source in sources]
