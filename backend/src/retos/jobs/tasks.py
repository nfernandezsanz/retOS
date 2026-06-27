import asyncio

from retos.api.routes.events import progress_store
from retos.core.config import get_settings
from retos.ingestion.text import fail_text_ingestion_job, run_text_ingestion
from retos.persistence.database import create_engine, create_session_factory, dispose_engine
from retos.persistence.unit_of_work import SQLAlchemyUnitOfWork
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
