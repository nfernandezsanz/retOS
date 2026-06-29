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
- Upload path traversal is constrained by sanitized basenames and per-upload storage
  directories; declared MIME spoofing for `.txt`, `.md`, and `.pdf` uploads is rejected
  before bytes are written or jobs are created. Both paths are covered by local tests.
- Tests do not require network access by default.

## Release Checks

- Backend tests pass with >= 90% total coverage and the current branch coverage ratchet;
  release promotion should raise the ratchet toward the 90% branch-only target.
- Frontend builds.
- Compose config validates.
- Compose topology validates that API, worker, and migrations share one backend image,
  and that API and worker share the same app environment plus persistent state volumes.
- Docker smoke validates that running API, worker, and migration containers share the
  same backend image ID.
- Docker images build.
- Docker stack smoke starts core services and hits API/web endpoints.
- Release readiness validates operations docs, safe defaults, and image topology.
- Release workflow validates GHCR publishing, SBOM/provenance, Cosign signing, and
  signature verification.
- Release note checks validate `CHANGELOG.md`, release-process guidance, and operator
  documentation links.
- Versioned release note checks validate concrete notes under `docs/releases/`.
- No secrets are baked into images.
- Migrations work from an empty database.

## Operations Notes

- Release images are tagged with `RETOS_IMAGE_TAG`; avoid mutable tags outside local
  development.
- Release candidates must update `CHANGELOG.md` and follow `docs/release-process.md`
  before tagging.
- Release candidates must add or update the matching `docs/releases/<version>.md` note
  with validation evidence, pending publish evidence, known limitations, and rollback
  guidance.
- Release tags publish `retos-backend` and `retos-web` to GHCR through
  `.github/workflows/release.yml`; the backend image remains shared by API, worker, and
  migrations.
- `api`, `worker`, and `migrate` must always share the backend image and may differ only
  by command; `api` and `worker` must also share the same backend state volume mounts.
- Backups must include Postgres, storage, eval reports, eval datasets, and optionally the
  rebuildable index volume.
- Restores must stop API/worker first, restore Postgres and volumes, run migrations, and
  then run health/smoke checks.
- `docs/operations.md` is the operator-facing source of truth for release, upgrade,
  backup, restore, health checks, and rollback.
