from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from retos.core.config import Settings
from retos.ingestion.text import content_hash, run_text_ingestion
from retos.persistence.bootstrap import bootstrap_admin_user
from retos.persistence.database import (
    SessionFactory,
    create_engine,
    create_schema,
    create_session_factory,
    dispose_engine,
)
from retos.persistence.unit_of_work import SQLAlchemyUnitOfWork
from retos.search.index import TantivySearchIndex
from retos.search.service import rebuild_domain_index

DEMO_DOMAIN_SLUG = "retos-demo"
DEMO_SOURCE_URI = "demo://retos/local-fixtures"
DEMO_ACTOR = "system:demo-seed"
UnitOfWorkFactory = Callable[[SessionFactory], SQLAlchemyUnitOfWork]


@dataclass(frozen=True)
class DemoDocument:
    external_id: str
    title: str
    text: str


@dataclass(frozen=True)
class DemoSeedResult:
    domain_id: str
    source_id: str
    created_documents: int
    skipped_documents: int
    index_job_id: str | None
    indexed_segments: int


DEMO_DOCUMENTS: tuple[DemoDocument, ...] = (
    DemoDocument(
        external_id="retos-demo-apollo-guidance",
        title="Apollo Guidance Notes",
        text=(
            "Apollo guidance computers used deterministic checklists, mission timers, "
            "and explicit operator procedures for critical navigation decisions. "
            "The operations team required traceable evidence before changing flight "
            "software or mission rules."
        ),
    ),
    DemoDocument(
        external_id="retos-demo-marine-biology",
        title="Marine Biology Field Notes",
        text=(
            "Ocean biology notes mention plankton, salinity, dissolved oxygen, and "
            "seasonal sampling windows. Researchers compare field observations with "
            "calibrated lab measurements before publishing a local evidence summary."
        ),
    ),
    DemoDocument(
        external_id="retos-demo-incident-policy",
        title="Incident Retention Policy",
        text=(
            "Incident response records must preserve operator actions, timestamps, "
            "system logs, reviewer notes, and final mitigation decisions for seven "
            "years. Escalation requires an audit journal entry and a linked evidence "
            "bundle."
        ),
    ),
)


async def ensure_demo_domain_and_source(
    *,
    uow: SQLAlchemyUnitOfWork,
    domain_slug: str,
    domain_name: str,
    source_name: str,
    source_uri: str,
) -> tuple[str, str]:
    async with uow:
        domain = await uow.domains.get_by_slug(domain_slug)
        if domain is None:
            domain = await uow.domains.add(
                slug=domain_slug,
                name=domain_name,
                description="Local seeded corpus for evaluating RetOS document workflows.",
            )
            await uow.journal_events.add(
                actor=DEMO_ACTOR,
                event_type="demo.domain.created",
                entity_type="domain",
                entity_id=domain.id,
                payload={"domain_id": domain.id, "domain_slug": domain.slug},
            )

        source = await uow.sources.get_by_domain_and_uri(domain.id, source_uri)
        if source is None:
            source = await uow.sources.add(
                domain_id=domain.id,
                kind="upload",
                name=source_name,
                uri=source_uri,
            )
            await uow.journal_events.add(
                actor=DEMO_ACTOR,
                event_type="demo.source.created",
                entity_type="source",
                entity_id=source.id,
                payload={"domain_id": domain.id, "source_id": source.id, "source_uri": source.uri},
            )

        await uow.commit()
        return domain.id, source.id


async def seed_demo_documents(
    *,
    uow_factory: UnitOfWorkFactory,
    session_factory: SessionFactory,
    domain_id: str,
    source_id: str,
    source_uri: str,
    documents: tuple[DemoDocument, ...] = DEMO_DOCUMENTS,
) -> tuple[int, int]:
    created = 0
    skipped = 0
    for document in documents:
        uow = uow_factory(session_factory)
        document_hash = content_hash(document.text)
        async with uow:
            existing = await uow.documents.get_by_domain_and_hash(domain_id, document_hash)
            if existing is not None:
                skipped += 1
                continue
            job = await uow.jobs.add(
                kind="ingest.source",
                status="queued",
                domain_id=domain_id,
                source_id=source_id,
                payload={
                    "source_id": source_id,
                    "title": document.title,
                    "text": document.text,
                    "source_uri": f"{source_uri}/{document.external_id}.txt",
                    "external_id": document.external_id,
                    "metadata": {"seed": "retos-demo", "external_id": document.external_id},
                    "max_segment_tokens": 80,
                },
            )
            await uow.journal_events.add(
                actor=DEMO_ACTOR,
                event_type="ingestion.queued",
                entity_type="job",
                entity_id=job.id,
                payload={
                    "kind": "text",
                    "domain_id": domain_id,
                    "source_id": source_id,
                    "title": document.title,
                    "seed": "retos-demo",
                },
            )
            await uow.progress_events.add(
                job_id=job.id,
                event_type="ingestion.queued",
                message=f"Queued demo text ingestion for {document.title}",
                payload={"title": document.title, "domain_id": domain_id, "seed": "retos-demo"},
            )
            await uow.commit()

        await run_text_ingestion(
            job_id=job.id,
            uow=uow_factory(session_factory),
            actor=DEMO_ACTOR,
        )
        created += 1
    return created, skipped


async def rebuild_demo_index(
    *,
    session_factory: SessionFactory,
    index_root: str,
    domain_id: str,
) -> tuple[str, int]:
    uow = SQLAlchemyUnitOfWork(session_factory)
    async with uow:
        job = await uow.jobs.add(
            kind="index.domain",
            status="queued",
            domain_id=domain_id,
            source_id=None,
            payload={"requested_by": "seed-demo", "seed": "retos-demo"},
        )
        await uow.journal_events.add(
            actor=DEMO_ACTOR,
            event_type="index.queued",
            entity_type="job",
            entity_id=job.id,
            payload={"domain_id": domain_id, "seed": "retos-demo"},
        )
        await uow.progress_events.add(
            job_id=job.id,
            event_type="index.queued",
            message="Queued demo BM25 index rebuild",
            payload={"domain_id": domain_id, "seed": "retos-demo"},
        )
        await uow.commit()

    result = await rebuild_domain_index(
        job_id=job.id,
        uow=SQLAlchemyUnitOfWork(session_factory),
        index=TantivySearchIndex(index_root),
        actor=DEMO_ACTOR,
    )
    return job.id, result.segment_count


async def seed_demo_corpus(
    *,
    session_factory: SessionFactory,
    index_root: str,
    domain_slug: str = DEMO_DOMAIN_SLUG,
    domain_name: str = "RetOS Demo",
    source_name: str = "Local demo fixtures",
    source_uri: str = DEMO_SOURCE_URI,
    rebuild_index: bool = True,
) -> DemoSeedResult:
    domain_id, source_id = await ensure_demo_domain_and_source(
        uow=SQLAlchemyUnitOfWork(session_factory),
        domain_slug=domain_slug,
        domain_name=domain_name,
        source_name=source_name,
        source_uri=source_uri,
    )
    created, skipped = await seed_demo_documents(
        uow_factory=SQLAlchemyUnitOfWork,
        session_factory=session_factory,
        domain_id=domain_id,
        source_id=source_id,
        source_uri=source_uri,
    )
    index_job_id = None
    indexed_segments = 0
    if rebuild_index:
        index_job_id, indexed_segments = await rebuild_demo_index(
            session_factory=session_factory,
            index_root=index_root,
            domain_id=domain_id,
        )
    return DemoSeedResult(
        domain_id=domain_id,
        source_id=source_id,
        created_documents=created,
        skipped_documents=skipped,
        index_job_id=index_job_id,
        indexed_segments=indexed_segments,
    )


async def run_seed(
    *,
    settings: Settings,
    domain_slug: str = DEMO_DOMAIN_SLUG,
    domain_name: str = "RetOS Demo",
    source_name: str = "Local demo fixtures",
    source_uri: str = DEMO_SOURCE_URI,
    create_tables: bool = False,
    rebuild_index: bool = True,
) -> DemoSeedResult:
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    try:
        if create_tables:
            await create_schema(engine)
        await bootstrap_admin_user(settings=settings, session_factory=session_factory)
        return await seed_demo_corpus(
            session_factory=session_factory,
            index_root=settings.index_root,
            domain_slug=domain_slug,
            domain_name=domain_name,
            source_name=source_name,
            source_uri=source_uri,
            rebuild_index=rebuild_index,
        )
    finally:
        await dispose_engine(engine)
