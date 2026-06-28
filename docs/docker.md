# Docker Images And Compose

RetOS is built as one shared backend image, one web image, and managed service images:

| Image | Dockerfile | Purpose |
| --- | --- | --- |
| `retos-backend` | `backend/Dockerfile`, target `backend-runtime` | Shared backend runtime for FastAPI API, Celery worker, and migrations. Different roles are selected through the entrypoint command. |
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
make image-size-check
```

Build tagged, traceable release images:

```bash
RETOS_IMAGE_TAG=2026.06.28 \
RETOS_VERSION=2026.06.28 \
RETOS_REVISION="$(git rev-parse HEAD)" \
RETOS_CREATED="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
docker compose build api web
```

The `api` service intentionally owns the only backend application build:
repository-root context, `backend/Dockerfile`, and `backend-runtime` target. The
`worker` and `migrate` services do not declare their own build; they reuse the same
`retos-backend` image tag and change only the entrypoint command. This avoids three
parallel backend builds for roles that share the same runtime.

The `migrate` service also uses `retos-backend` and runs `command: ["migrate"]`.
It applies `alembic upgrade head` before API and worker start.

Both application images include OCI labels for source repository, documentation, MIT
license, version, revision, and build creation time. Compose passes these build args:

| Build Arg | Default | Purpose |
| --- | --- | --- |
| `RETOS_VERSION` | `local` | Human release or package version. |
| `RETOS_REVISION` | `unknown` | Git commit SHA or source revision. |
| `RETOS_CREATED` | `unknown` | Build timestamp, preferably RFC 3339 UTC. |

CI enforces this topology with `scripts/check_docker_topology.sh`: `api`, `worker`,
and `migrate` must resolve to the same backend image, only `api` may declare the
backend build using `backend/Dockerfile` from the repository root, the target must
be `backend-runtime`, and each role may differ only by command. Docker stack smoke
also runs `scripts/check_backend_runtime_image.sh`
after startup so the running `api`, `worker`, and `migrate` containers must share
the exact same Docker image ID, not just equivalent source files.

CI also runs `scripts/check_image_metadata.sh` so release images cannot lose their
OCI labels. Docker smoke inspects the built `retos-backend` and `retos-web` images.

CI and Docker smoke also run `scripts/check_image_size.sh`. The source check documents
the current image budgets, and the built-image check fails when a release image grows
past the configured byte limit:

| Image | Default Budget | Override |
| --- | ---: | --- |
| `retos-backend` | `1,400,000,000` bytes | `RETOS_BACKEND_IMAGE_MAX_BYTES` |
| `retos-web` | `200,000,000` bytes | `RETOS_WEB_IMAGE_MAX_BYTES` |

The backend budget intentionally allows Python 3.14, OCR, PDF, and search runtime
dependencies while still catching accidental build-context leaks or duplicate runtime
layers. The web budget allows the Nginx runtime plus compiled React assets.

## Publish

`.github/workflows/release.yml` publishes release images to GHCR:

| Image | Registry Package |
| --- | --- |
| `retos-backend` | `ghcr.io/<owner>/retos-backend` |
| `retos-web` | `ghcr.io/<owner>/retos-web` |

The workflow builds the same `backend-runtime` target used by Compose, so API, worker,
and migrate continue to share one backend image after publishing. It also requests SBOM
and max-mode provenance attestations from `docker/build-push-action`, then signs the
published digests with Cosign keyless signing. Release readiness runs
`scripts/check_release_workflow.sh` so the publishing, SBOM, provenance, and Cosign
contract stays documented. The publish job depends on backend format/lint/type/test/eval
smoke and frontend checks, so a tag cannot push images before the core quality gates pass.

## Smoke Test

Run the same Docker smoke used by CI:

```bash
make docker-smoke
```

The smoke test uses a temporary Compose project, builds the app images, runs migrations,
starts Postgres, RabbitMQ, API, worker, and web, creates a small mounted
`.txt`/`.md`/`.pdf` corpus in the shared storage volume, creates tiny SQuAD, HotpotQA,
Natural Questions, and OCR benchmark fixtures in the eval dataset volume, waits for
healthchecks, hits health, auth, domain/source/document/artifact/segment CRUD, mounted
source scan through the worker, text ingestion through the worker, file upload ingestion
through the worker, BM25 index rebuild through the worker, search, local and
dataset-backed eval endpoints with report export, job lifecycle transitions, persisted
audit endpoints, SSE, and web over HTTP, then removes its temporary containers and
volumes.

When the stack is already running, validate the backend runtime image contract directly:

```bash
make docker-runtime-image-check
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

Dataset-backed eval APIs only read dataset files under `RETOS_EVAL_DATASET_ROOT` and
write reports under `RETOS_EVAL_REPORT_ROOT`.

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
