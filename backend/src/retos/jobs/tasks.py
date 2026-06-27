from retos.api.routes.events import progress_store
from retos.worker import celery_app


@celery_app.task(name="retos.jobs.ping")  # type: ignore[untyped-decorator]
def ping() -> str:
    progress_store.append("job.ping", {"status": "ok"})
    return "pong"
