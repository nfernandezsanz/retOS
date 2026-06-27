from celery import Celery

from retos.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "retos",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["retos.jobs.tasks"],
)

celery_app.conf.update(
    task_default_queue="retos",
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)
