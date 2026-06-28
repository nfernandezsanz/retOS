# Open Source And Docker

## Goal

RetOS should be easy to clone, test, build, and run as a local Docker stack.

## Services

| Service | Purpose |
| --- | --- |
| `api` | FastAPI REST/SSE API. |
| `worker` | Celery worker for long jobs, running the same backend image as `api` with a different command. |
| `web` | React console served by Nginx. |
| `postgres` | Durable catalog, jobs, journals, and ledgers. |
| `rabbitmq` | Celery broker. |
| `ollama` | Local LLM runtime. |

## Volumes

| Volume | Content |
| --- | --- |
| `retos_postgres` | Database data. |
| `retos_rabbitmq` | Broker state. |
| `retos_storage` | Raw files and artifacts. |
| `retos_index` | Rebuildable search indexes. |
| `retos_ollama` | Ollama models. |
| `retos_eval_datasets` | Operator-provided local eval datasets and samples. |
| `retos_eval_reports` | Exported JSON/Markdown eval reports. |

## Security Defaults

- API keys are environment variables only.
- Paid LLMs are disabled by default.
- Development admin credentials are rejected in production.
- Upload size limits are configurable.
- Path traversal and MIME spoofing must be tested.
- Tests do not require network access by default.

## Release Checks

- Backend tests pass with >= 90% line and branch coverage.
- Frontend builds.
- Compose config validates.
- Compose topology validates that API, worker, and migrations share one backend image.
- Docker images build.
- Docker stack smoke starts core services and hits API/web endpoints.
- Release readiness validates operations docs, safe defaults, and image topology.
- Release note checks validate `CHANGELOG.md`, release-process guidance, and operator
  documentation links.
- No secrets are baked into images.
- Migrations work from an empty database.

## Operations Notes

- Release images are tagged with `RETOS_IMAGE_TAG`; avoid mutable tags outside local
  development.
- Release candidates must update `CHANGELOG.md` and follow `docs/release-process.md`
  before tagging.
- `api`, `worker`, and `migrate` must always share the backend image and may differ only
  by command.
- Backups must include Postgres, storage, eval reports, eval datasets, and optionally the
  rebuildable index volume.
- Restores must stop API/worker first, restore Postgres and volumes, run migrations, and
  then run health/smoke checks.
- `docs/operations.md` is the operator-facing source of truth for release, upgrade,
  backup, restore, health checks, and rollback.
