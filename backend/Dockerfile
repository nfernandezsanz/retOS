# syntax=docker/dockerfile:1.7

FROM python:3.14-slim AS runtime

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
COPY infra/docker/backend-entrypoint.sh /usr/local/bin/retos-backend
RUN chmod +x /usr/local/bin/retos-backend \
    && groupadd --system --gid "${APP_GID}" retos \
    && useradd --system --uid "${APP_UID}" --gid retos --home-dir /nonexistent retos \
    && mkdir -p /var/lib/retos/storage /var/lib/retos/index /var/lib/retos/evals/datasets /var/lib/retos/evals/reports \
    && chown -R retos:retos /app /var/lib/retos

ENV PYTHONPATH=/app/backend/src

USER retos
EXPOSE 8000

ENTRYPOINT ["retos-backend"]
CMD ["api"]
