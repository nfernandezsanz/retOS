# Docker Images And Compose

RetOS is built as one shared backend image, one web image, and managed service images:

| Image | Dockerfile | Purpose |
| --- | --- | --- |
| `retos-backend` | `backend/Dockerfile` | Shared backend runtime for both FastAPI API and Celery worker. Different roles are selected through the entrypoint command. |
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
docker compose build api web
```

The `worker` service intentionally does not have its own build. It runs the exact same `retos-backend` image built by the `api` service with `command: ["worker"]`.

## Smoke Test

Run the same Docker smoke used by CI:

```bash
make docker-smoke
```

The smoke test uses a temporary Compose project, builds the app images, starts Postgres, RabbitMQ, API, worker, and web, waits for healthchecks, hits the API and web over HTTP, then removes its temporary containers and volumes.

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
- `postgres:18-bookworm` stores data under a major-version-aware directory, so the volume is mounted at `/var/lib/postgresql`, not `/var/lib/postgresql/data`.

## Local Limitation

If Docker Desktop or the Docker daemon is not running, `docker compose build` will fail even when `docker compose config` is valid.
