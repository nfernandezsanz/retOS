# syntax=docker/dockerfile:1.7

FROM python:3.14-slim AS backend-base

ARG APP_UID=10001
ARG APP_GID=10001

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive \
    RETOS_STORAGE_ROOT=/var/lib/retos/storage \
    RETOS_INDEX_ROOT=/var/lib/retos/index \
    RETOS_EVAL_DATASET_ROOT=/var/lib/retos/evals/datasets \
    RETOS_EVAL_REPORT_ROOT=/var/lib/retos/evals/reports

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      libgl1 \
      libglib2.0-0 \
      tesseract-ocr \
      tesseract-ocr-eng \
      tesseract-ocr-spa \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/backend/requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install -r /app/backend/requirements.txt

COPY backend/alembic.ini /app/backend/alembic.ini
COPY backend/alembic /app/backend/alembic
COPY backend/src /app/backend/src
COPY backend/scripts/seed_demo.py /app/backend/scripts/
COPY infra/docker/backend-entrypoint.sh /usr/local/bin/retos-backend
RUN chmod +x /usr/local/bin/retos-backend \
    && groupadd --gid "${APP_GID}" retos \
    && useradd --uid "${APP_UID}" --gid retos --home-dir /nonexistent --no-create-home --shell /usr/sbin/nologin retos \
    && mkdir -p /var/lib/retos/storage /var/lib/retos/index /var/lib/retos/evals/datasets /var/lib/retos/evals/reports \
    && chown -R retos:retos /app /var/lib/retos

ENV PYTHONPATH=/app/backend/src

USER retos
EXPOSE 8000

FROM backend-base AS backend-runtime

ARG RETOS_VERSION=local
ARG RETOS_REVISION=unknown
ARG RETOS_CREATED=unknown

LABEL org.opencontainers.image.title="RetOS Backend" \
      org.opencontainers.image.description="Shared FastAPI, Celery worker, and migration runtime for RetOS" \
      org.opencontainers.image.source="https://github.com/nfernandezsanz/retOS" \
      org.opencontainers.image.url="https://github.com/nfernandezsanz/retOS" \
      org.opencontainers.image.documentation="https://github.com/nfernandezsanz/retOS/blob/main/docs/docker.md" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${RETOS_VERSION}" \
      org.opencontainers.image.revision="${RETOS_REVISION}" \
      org.opencontainers.image.created="${RETOS_CREATED}"

ENTRYPOINT ["retos-backend"]
CMD ["api"]
