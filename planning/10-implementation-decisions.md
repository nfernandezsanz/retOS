# Implementation Decisions

Last updated: 2026-06-27

| Topic | Decision |
| --- | --- |
| License | MIT |
| Repository | Single monorepo |
| Python | 3.14 |
| Backend | FastAPI, Pydantic v2, SQLAlchemy 2 async, Alembic |
| Frontend | React, TypeScript, Vite |
| Streaming | Server-Sent Events |
| Admin | Bootstrap admin plus React Settings/Admin views |
| Queue | Celery with RabbitMQ |
| Durable state | Postgres |
| Persistence pattern | SQLAlchemy async repositories behind a Unit of Work |
| Search | Tantivy through an adapter |
| OCR | Local OCR in the MVP |
| Agent runtime | `deepagents.create_deep_agent` |
| Local LLM | Ollama `gemma4` |
| Tests | 90% line and branch coverage, no paid providers by default |

## Backend Decision

Use FastAPI instead of Django. RetOS needs live, process-centric workflows rather than model-centric admin CRUD. React is the product console, and FastAPI keeps async/SSE straightforward.

## Queue Decision

Use Celery with RabbitMQ. RetOS has long-running, retryable jobs: scan, hash, OCR, extraction, segmentation, indexing, evals, and potentially long agent runs.

## Search Decision

Use Tantivy first. It provides local BM25 search without adding OpenSearch operational weight to the MVP.

## Repository Layout

```text
backend/
frontend/
docs/
infra/
planning/
evals/
```

Rules:

- Domain code should not import FastAPI, Celery, SDKs, or SQLAlchemy directly.
- External systems must sit behind adapters.
- Tests must mock providers by default.
- Docker is part of the development contract.
- API smoke should exercise real HTTP endpoints for each product-visible slice.
