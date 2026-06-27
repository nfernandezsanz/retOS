# RetOS

RetOS is a local-first research system for auditable document investigation. It is designed to run as a reusable Docker stack with a React console, a FastAPI backend, Celery workers backed by RabbitMQ, Postgres persistence, Tantivy BM25 search, local OCR, and a Deep Agents research runtime.

The source of truth is the versioned corpus store. Search indexes are rebuildable projections, not the canonical record.

## What This Repository Contains

- A Python 3.14 FastAPI backend scaffold with secure settings, JWT helpers, Argon2 password hashing, SSE progress streaming, and Celery/RabbitMQ wiring.
- A React + TypeScript + Vite frontend scaffold focused on operational visibility for documents, jobs, OCR, indexing, and agent runs.
- Docker Compose for Postgres, RabbitMQ, Ollama, API, worker, and web services.
- Planning, ADRs, and architecture assets for the open source implementation path.
- Test and coverage defaults that avoid paid LLM calls.

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
```

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

This is the foundation commit for the open source implementation. The next milestone is Phase 0 completion: CI green, Docker smoke tests, and the first domain/document persistence slice.
