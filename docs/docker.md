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

The `worker` service intentionally does not have its own build or Dockerfile. It runs the exact same `retos-backend` image built by the `api` service with `command: ["worker"]`.

The `migrate` service also uses `retos-backend` and runs `command: ["migrate"]`.
It applies `alembic upgrade head` before API and worker start.

CI enforces this topology with `scripts/check_docker_topology.sh`: `api`, `worker`,
and `migrate` must resolve to the same backend image, only `api` may declare the
shared backend build, the backend build must use `backend/Dockerfile` from the
repository root, and each role may differ only by command.

## Smoke Test

Run the same Docker smoke used by CI:

```bash
make docker-smoke
```

The smoke test uses a temporary Compose project, builds the app images, runs migrations, starts Postgres, RabbitMQ, API, worker, and web, creates a small mounted `.txt`/`.md`/`.pdf` corpus in the shared storage volume, creates a tiny SQuAD fixture in the eval dataset volume, waits for healthchecks, hits health, auth, domain/source/document/artifact/segment CRUD, mounted source scan through the worker, text ingestion through the worker, file upload ingestion through the worker, BM25 index rebuild through the worker, search, local and SQuAD eval endpoints with report export, job lifecycle transitions, persisted audit endpoints, SSE, and web over HTTP, then removes its temporary containers and volumes.

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

## LLM Provider Configuration

The default Docker profile is local-first:

- `RETOS_PROVIDER=local`
- `RETOS_MODEL=ollama:gemma4`
- `RETOS_AGENT_RUNTIME=deterministic`
- `RETOS_OLLAMA_MODEL=gemma4`
- `RETOS_ALLOW_PAID_LLM=false`

API, worker, and migrate share the same `retos-backend` image, Python dependencies, OCR
runtime, provider environment, and mounted storage roots. The API writes uploaded files
under `RETOS_STORAGE_ROOT`; the worker reads those same files from the same named volume.
Non-secret provider settings are declared in `docker-compose.yml`; API keys come from a
real `.env` file and are not present in `.env.example`.

Eval datasets and report exports are mounted separately from the corpus and index:

- `retos_eval_datasets` -> `/var/lib/retos/evals/datasets`
- `retos_eval_reports` -> `/var/lib/retos/evals/reports`

The SQuAD admin API only reads dataset files under `RETOS_EVAL_DATASET_ROOT` and writes
reports under `RETOS_EVAL_REPORT_ROOT`.

Paid providers remain blocked until both conditions are true:

- The provider-specific key/configuration is present in `.env`.
- `RETOS_ALLOW_PAID_LLM=true` is set explicitly.

Enable real Deep Agents synthesis only after the local model is available:

```bash
docker compose --profile models run --rm ollama-pull
RETOS_AGENT_RUNTIME=deepagents docker compose up --build
```

The API and worker still use the same backend image and the same controlled corpus tools;
the runtime switch changes answer synthesis, not storage, indexing, or job semantics.

## Runtime Roles

The backend image uses `infra/docker/backend-entrypoint.sh`.

```bash
docker compose run --rm api api
docker compose run --rm worker worker
docker compose run --rm migrate migrate
```

The image defaults to the `api` role.

## Database Migrations

Compose runs migrations automatically through the one-shot `migrate` service. For local
development outside Docker:

```bash
make db-upgrade
make db-downgrade
```

See [database.md](database.md) for schema and migration details.

## Security Notes

- Application containers run as non-root users.
- The backend image installs local OCR support for English and Spanish.
- `.dockerignore` excludes secrets, local volumes, virtualenvs, caches, tests, planning docs, and generated frontend assets.
- RabbitMQ carries lightweight job messages only. Celery task results are ignored by default, and worker remote-control gossip/mingle is disabled for RabbitMQ 4 compatibility; durable job status, documents, and artifacts belong in Postgres-backed metadata and storage volumes.
- Development passwords in `.env.example` must be changed for anything beyond local use.
- `postgres:18-bookworm` stores data under a major-version-aware directory, so the volume is mounted at `/var/lib/postgresql`, not `/var/lib/postgresql/data`.

## Local Limitation

If Docker Desktop or the Docker daemon is not running, `docker compose build` will fail even when `docker compose config` is valid.
