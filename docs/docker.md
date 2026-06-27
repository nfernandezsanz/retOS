# Docker Images And Compose

RetOS is built as two application images plus managed service images:

| Image | Dockerfile | Purpose |
| --- | --- | --- |
| `retos-api` / `retos-worker` | `backend/Dockerfile` | FastAPI API and Celery worker. The same image runs different roles through the entrypoint. |
| `retos-web` | `frontend/Dockerfile` | React static assets served by Nginx. |
| `postgres:18-bookworm` | upstream | Durable catalog, jobs, journals, ledgers, and manifests. |
| `rabbitmq:4-management` | upstream | Celery broker. |
| `ollama/ollama:latest` | upstream | Local LLM runtime. |

## Build

```bash
docker compose build
```

Build only application images:

```bash
docker compose build api worker web
```

## Run

```bash
cp .env.example .env
docker compose up --build
```

Open:

- Web UI: http://localhost:8080
- API: http://localhost:8000
- API docs: http://localhost:8000/docs
- RabbitMQ management: http://localhost:15672

## Pull The Local Model

```bash
docker compose --profile models run --rm ollama-pull
```

Equivalent manual command:

```bash
docker compose exec ollama ollama pull gemma4
```

## Runtime Roles

The backend image uses `infra/docker/backend-entrypoint.sh`.

```bash
docker compose run --rm api api
docker compose run --rm worker worker
```

The image defaults to the `api` role.

## Security Notes

- Application containers run as non-root users.
- The backend image installs local OCR support for English and Spanish.
- `.dockerignore` excludes secrets, local volumes, virtualenvs, caches, tests, planning docs, and generated frontend assets.
- RabbitMQ carries lightweight job messages only. Documents and artifacts belong in Postgres-backed metadata and storage volumes.
- Development passwords in `.env.example` must be changed for anything beyond local use.

## Local Limitation

If Docker Desktop or the Docker daemon is not running, `docker compose build` will fail even when `docker compose config` is valid.
