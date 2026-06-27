#!/usr/bin/env sh
set -eu

role="${1:-api}"

case "$role" in
  api)
    exec uvicorn retos.main:app --host "${RETOS_API_HOST:-0.0.0.0}" --port "${RETOS_API_PORT:-8000}"
    ;;
  worker)
    exec celery -A retos.worker.celery_app worker --loglevel=INFO
    ;;
  *)
    exec "$@"
    ;;
esac
