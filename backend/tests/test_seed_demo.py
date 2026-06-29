from __future__ import annotations

from pathlib import Path

import pytest

from retos.core.config import Settings
from retos.demo.seed import run_seed
from retos.persistence.database import create_engine, create_session_factory, dispose_engine
from retos.persistence.unit_of_work import SQLAlchemyUnitOfWork
from retos.search.index import TantivySearchIndex


@pytest.mark.asyncio
async def test_seed_demo_creates_auditable_searchable_fixture(
    tmp_path: Path,
    settings: Settings,
) -> None:
    local_settings = settings.model_copy(
        update={
            "database_url": f"sqlite+aiosqlite:///{tmp_path / 'seed-demo.db'}",
            "index_root": str(tmp_path / "index"),
        }
    )

    result = await run_seed(settings=local_settings, create_tables=True)

    assert result.created_documents == 3
    assert result.skipped_documents == 0
    assert result.index_job_id is not None
    assert result.indexed_segments >= 3
    hits = TantivySearchIndex(local_settings.index_root).search_domain(
        result.domain_id,
        "Apollo guidance",
    )
    assert hits
    assert hits[0].title == "Apollo Guidance Notes"

    engine = create_engine(local_settings.database_url)
    session_factory = create_session_factory(engine)
    try:
        async with SQLAlchemyUnitOfWork(session_factory) as uow:
            documents = await uow.documents.list_for_domain(result.domain_id)
            jobs = await uow.jobs.list(limit=10)
            journal_events = await uow.journal_events.list(limit=20)
            progress_events = await uow.progress_events.list(limit=20)
    finally:
        await dispose_engine(engine)

    assert len(documents) == 3
    assert any(job.kind == "index.domain" and job.status == "succeeded" for job in jobs)
    assert any(event.event_type == "demo.domain.created" for event in journal_events)
    assert any(event.event_type == "document.ingested" for event in journal_events)
    assert any(event.event_hash for event in journal_events)
    assert any(event.event_type == "index.completed" for event in progress_events)
    assert any(event.event_hash for event in progress_events)


@pytest.mark.asyncio
async def test_seed_demo_is_idempotent(
    tmp_path: Path,
    settings: Settings,
) -> None:
    local_settings = settings.model_copy(
        update={
            "database_url": f"sqlite+aiosqlite:///{tmp_path / 'seed-demo-idempotent.db'}",
            "index_root": str(tmp_path / "index"),
        }
    )

    first = await run_seed(settings=local_settings, create_tables=True)
    second = await run_seed(settings=local_settings, create_tables=True)

    assert first.created_documents == 3
    assert second.domain_id == first.domain_id
    assert second.source_id == first.source_id
    assert second.created_documents == 0
    assert second.skipped_documents == 3
    assert second.indexed_segments == first.indexed_segments


@pytest.mark.asyncio
async def test_seed_demo_can_skip_index_rebuild_after_schema_exists(
    tmp_path: Path,
    settings: Settings,
) -> None:
    local_settings = settings.model_copy(
        update={
            "database_url": f"sqlite+aiosqlite:///{tmp_path / 'seed-demo-no-index.db'}",
            "index_root": str(tmp_path / "index"),
        }
    )

    first = await run_seed(
        settings=local_settings,
        create_tables=True,
        rebuild_index=False,
    )
    second = await run_seed(
        settings=local_settings,
        create_tables=False,
        rebuild_index=False,
    )

    assert first.created_documents == 3
    assert first.index_job_id is None
    assert first.indexed_segments == 0
    assert second.domain_id == first.domain_id
    assert second.created_documents == 0
    assert second.skipped_documents == 3
    assert second.index_job_id is None
