# RetOS

RetOS is a local-first research system for auditable document investigation. It is designed to run as a reusable Docker stack with a React console, a FastAPI backend, Celery workers backed by RabbitMQ, Postgres persistence, Tantivy BM25 search, local OCR, and a Deep Agents research runtime.

The source of truth is the versioned corpus store. Search indexes are rebuildable projections, not the canonical record.

## Current Status

| Signal | Status |
| --- | --- |
| Product maturity | Pre-alpha foundation. Core product slices are being built phase by phase. |
| Backend coverage | 92.50% line/branch coverage on the current scaffold. |
| Stability | Green foundation: format, PEP 8, typecheck, tests, API smoke, frontend build, browser smoke, Docker build, migrations, and Docker stack smoke are enforced. |
| Default cost profile | Zero paid LLM calls. Paid providers are disabled unless explicitly enabled. |
| Runtime model | Docker-first local stack with Postgres, RabbitMQ, Ollama, API, worker, and web UI. |
| Next milestone | Phase 1: core domain persistence, jobs, journals, progress events, and admin persistence. |

This repository is intentionally being built as a staff-engineer-quality reference project: decisions are documented, quality gates are automated, integration checks hit real endpoints, UI smoke tests open the actual frontend, and every implementation phase is expected to leave behind tests, auditability, and operating notes.

## What This Repository Contains

- A Python 3.14 FastAPI backend scaffold with secure settings, JWT helpers, Argon2 password hashing, SSE progress streaming, and Celery/RabbitMQ wiring.
- Initial SQLAlchemy async persistence for domain and source management through a Unit of Work.
- Alembic migrations for domains, sources, documents, versions, artifacts, segments, jobs, progress events, and audit journals.
- Durable documents API with immutable initial versions, audit journal entries, progress events, and live SSE notifications.
- Durable jobs API with persisted job, journal, progress-event records, and live SSE notifications.
- A React + TypeScript + Vite frontend scaffold focused on operational visibility for documents, jobs, OCR, indexing, and agent runs.
- Docker Compose for Postgres, RabbitMQ, Ollama, API, worker, and web services.
- Planning, ADRs, and architecture assets for the open source implementation path.
- Test and coverage defaults that avoid paid LLM calls.
- CI jobs that validate backend format, PEP 8, types, tests, API smoke, frontend build, browser smoke, Docker build, and Docker stack smoke.

## Development Model

RetOS is designed to be developed primarily with autonomous coding agents such as Codex and Claude, with limited human interaction and strong written constraints. The repository is structured so agents can work from durable artifacts instead of relying on ad hoc chat memory:

- `planning/` defines the roadmap, phase gates, testing policy, UI plan, auditability model, and implementation decisions.
- `docs/adr/` records architectural decisions before they sprawl through the codebase.
- `README.md`, `docs/docker.md`, and `CONTRIBUTING.md` describe how to build, test, run, and validate the system.
- CI is expected to catch formatting, PEP 8, type, coverage, API, frontend, and browser regressions.
- Agents should update plans, tests, docs, and ADRs in the same change when behavior or architecture changes.

The intended loop is:

```text
read planning and ADRs
  -> implement the smallest coherent slice
  -> run Black continuously
  -> run unit, integration, API smoke, and browser smoke checks
  -> update docs and tracker
  -> commit with a clear message
```

## Architecture

![RetOS architecture](docs/assets/architecture.svg)

```text
documents/uploads/mounts
  -> versioned corpus store
  -> reproducible ingest pipeline
  -> Tantivy BM25 + metadata indexes
  -> Deep Agents research runtime
  -> cited answer + evidence ledger + audit journal
```

## Stack

| Area | Choice |
| --- | --- |
| Backend | Python 3.14, FastAPI, Pydantic v2, SQLAlchemy 2 async, Alembic |
| Queue | Celery with RabbitMQ |
| Database | Postgres |
| Search | Tantivy via adapter |
| OCR | Local OCR pipeline with PyMuPDF, Tesseract, and pytesseract |
| Agent runtime | Deep Agents |
| Local LLM | Ollama with `gemma4` |
| Frontend | React 19, TypeScript, Vite, TanStack Query, TanStack Router |
| Streaming | Server-Sent Events |
| License | MIT |

## Quick Start

Copy the example environment and change the secrets before using anything beyond local development:

```bash
cp .env.example .env
```

Start the full stack:

```bash
docker compose up --build
```

Services:

| Service | URL |
| --- | --- |
| Web UI | http://localhost:8080 |
| API | http://localhost:8000 |
| API docs | http://localhost:8000/docs |
| RabbitMQ management | http://localhost:15672 |
| Ollama | http://localhost:11434 |

Pull the default local model:

```bash
docker compose --profile models run --rm ollama-pull
```

More Docker details are in [docs/docker.md](docs/docker.md).
API integration details are in [docs/api-integration.md](docs/api-integration.md).
Database and migration details are in [docs/database.md](docs/database.md).

## Development

Install backend dependencies:

```bash
python3 -m pip install -r backend/requirements-dev.txt
```

Run backend checks:

```bash
make format-check
make lint
make typecheck
make test
make api-smoke
```

Apply local database migrations:

```bash
make db-upgrade
```

Format backend code while working:

```bash
make format
```

Install and check the frontend:

```bash
cd frontend
npm install
npm run check
npm run e2e
```

Run the full local validation loop:

```bash
make check
make integration
make frontend-test
make frontend-e2e
docker compose --env-file .env.example config
docker compose --dry-run build
make docker-smoke
```

## Quality Gates

Every meaningful change should pass these gates:

| Gate | Command | Purpose |
| --- | --- | --- |
| Backend format | `make format-check` | Enforces Black formatting. |
| Backend PEP 8/lint | `make lint` | Uses Ruff for PEP 8 and bug-prone patterns. |
| Backend types | `make typecheck` | Enforces strict mypy on `src`. |
| Backend tests | `make test` | Runs pytest with 90% coverage gate. |
| API smoke | `make api-smoke` | Starts Uvicorn and hits health, auth, domain/source/document CRUD, job creation/listing, and SSE over HTTP. |
| Frontend build | `make frontend-test` | TypeScript build plus Vite production build. |
| Browser smoke | `make frontend-e2e` | Opens the React console with Playwright and verifies visible UI state. |
| Compose config | `docker compose --env-file .env.example config` | Validates the Docker stack definition. |
| Image dry run | `docker compose --dry-run build` | Validates image build graph without requiring a running daemon. |
| Docker stack smoke | `make docker-smoke` | Builds images, runs migrations, starts Postgres/RabbitMQ/API/worker/web, and hits health, auth, domain/source/document CRUD, job creation/listing, SSE, and web over HTTP. |

## Security Defaults

- Paid providers are disabled by default with `RETOS_ALLOW_PAID_LLM=false`.
- The production JWT secret must be at least 32 characters and must not use the development placeholder.
- A default bootstrap admin password is allowed only in development.
- Passwords are hashed with Argon2 through `pwdlib`.
- JWTs include issuer, audience, issue time, not-before time, and expiration.
- CORS is explicit; wildcard origins are rejected outside development.
- RabbitMQ carries job commands and IDs only. Documents and artifacts stay in Postgres-backed metadata and storage volumes.

## Repository Layout

```text
backend/      FastAPI API, Celery worker, domain-facing services, tests
frontend/     React console
docs/         ADRs and architecture assets
infra/        Docker entrypoints and runtime config
planning/     Implementation plan and phase tracker
evals/        Future local evaluation datasets and reports
```

## Project Status

The foundation is in place and CI should remain green before feature work proceeds. The project is not product-complete yet; it is a deliberately staged implementation. The next milestone is Phase 1: persistent domain/document/job/audit foundations with integration tests and UI-visible progress.
