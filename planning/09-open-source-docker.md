# Open Source And Docker

## Goal

RetOS should be easy to clone, test, build, and run as a local Docker stack.

## Services

| Service | Purpose |
| --- | --- |
| `api` | FastAPI REST/SSE API. |
| `worker` | Celery worker for long jobs. |
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
- Docker images build.
- No secrets are baked into images.
- Migrations work from an empty database.
