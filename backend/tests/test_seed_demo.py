from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from retos.core.config import Settings
from retos.persistence.database import create_engine, create_session_factory, dispose_engine
from retos.persistence.unit_of_work import SQLAlchemyUnitOfWork
from retos.search.index import TantivySearchIndex


def load_seed_demo() -> ModuleType:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "seed_demo.py"
    spec = importlib.util.spec_from_file_location("seed_demo", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load seed demo script from {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_seed_demo_creates_auditable_searchable_fixture(
    tmp_path: Path,
    settings: Settings,
) -> None:
    seed_demo = load_seed_demo()
    local_settings = settings.model_copy(
        update={
            "database_url": f"sqlite+aiosqlite:///{tmp_path / 'seed-demo.db'}",
            "index_root": str(tmp_path / "index"),
        }
    )

    result = await seed_demo.run_seed(settings=local_settings, create_tables=True)

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
    seed_demo = load_seed_demo()
    local_settings = settings.model_copy(
        update={
            "database_url": f"sqlite+aiosqlite:///{tmp_path / 'seed-demo-idempotent.db'}",
            "index_root": str(tmp_path / "index"),
        }
    )

    first = await seed_demo.run_seed(settings=local_settings, create_tables=True)
    second = await seed_demo.run_seed(settings=local_settings, create_tables=True)

    assert first.created_documents == 3
    assert second.domain_id == first.domain_id
    assert second.source_id == first.source_id
    assert second.created_documents == 0
    assert second.skipped_documents == 3
    assert second.indexed_segments == first.indexed_segments
