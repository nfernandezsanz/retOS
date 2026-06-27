import asyncio

from retos.api.routes.events import progress_store
from retos.core.config import get_settings
from retos.ingestion.text import fail_text_ingestion_job, run_text_ingestion
from retos.persistence.database import create_engine, create_session_factory, dispose_engine
from retos.persistence.unit_of_work import SQLAlchemyUnitOfWork
from retos.search.index import TantivySearchIndex
from retos.search.service import fail_index_job, rebuild_domain_index
from retos.worker import celery_app


@celery_app.task(name="retos.jobs.ping")  # type: ignore[untyped-decorator]
def ping() -> str:
    progress_store.append("job.ping", {"status": "ok"})
    return "pong"


async def _run_text_ingestion_task(job_id: str) -> str:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    uow = SQLAlchemyUnitOfWork(session_factory)
    try:
        result = await run_text_ingestion(job_id=job_id, uow=uow)
        return result.document.id
    except Exception as exc:
        await fail_text_ingestion_job(
            job_id=job_id,
            uow=SQLAlchemyUnitOfWork(session_factory),
            error=str(exc),
        )
        raise
    finally:
        await dispose_engine(engine)


@celery_app.task(name="retos.jobs.ingest_text")  # type: ignore[untyped-decorator]
def ingest_text_job(job_id: str) -> str:
    return asyncio.run(_run_text_ingestion_task(job_id))


async def _rebuild_domain_index_task(job_id: str) -> int:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    uow = SQLAlchemyUnitOfWork(session_factory)
    try:
        result = await rebuild_domain_index(
            job_id=job_id,
            uow=uow,
            index=TantivySearchIndex(settings.index_root),
        )
        return result.segment_count
    except Exception as exc:
        await fail_index_job(
            job_id=job_id,
            uow=SQLAlchemyUnitOfWork(session_factory),
            error=str(exc),
        )
        raise
    finally:
        await dispose_engine(engine)


@celery_app.task(name="retos.jobs.rebuild_domain_index")  # type: ignore[untyped-decorator]
def rebuild_domain_index_job(job_id: str) -> int:
    return asyncio.run(_rebuild_domain_index_task(job_id))
