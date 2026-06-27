# Roadmap Phases

Every phase must pass implementation, tests, auditability, and documentation checks.

## Phase 0 - Open Source Bootstrap

Deliverables:

- MIT license.
- Monorepo layout.
- FastAPI backend scaffold.
- React frontend scaffold.
- Docker Compose with Postgres, RabbitMQ, Ollama, API, worker, and web.
- CI with lint, typecheck, tests, and coverage.
- ADRs for major decisions.

Exit criteria:

- A contributor can clone, install dependencies, run tests, and inspect the Docker stack without secrets.

## Phase 1 - Core Domain And Persistence

Deliverables:

- Domain models for domains, sources, documents, versions, artifacts, segments, jobs, journals, and progress events.
- SQLAlchemy async repositories and Alembic migrations.
- Unit of Work.
- Bootstrap admin persistence.

Exit criteria:

- A domain/source can be registered and document versions can be persisted idempotently.

## Phase 2 - Ingestion, OCR, And BM25

Deliverables:

- Incremental scan.
- Extractors for `.txt`, `.md`, and `.pdf`.
- Local OCR profile for scanned pages/images.
- Deterministic segmentation.
- Tantivy index adapter.
- Celery jobs for scan, OCR, extraction, segmentation, and indexing.

Exit criteria:

- A fixture corpus can be ingested twice without duplicates and searched with stable anchors.

## Phase 3 - Deep Agents Runtime

Deliverables:

- `deepagents.create_deep_agent` entrypoint.
- Controlled research tools.
- Provider abstraction with fake, Ollama, and paid-provider adapters.
- Query budgets and SSE run timeline.
- Evidence ledger validation.

Exit criteria:

- A fixture question produces a cited answer, verifiable ledger, and auditable tool timeline.

## Phase 4 - Product UI

Deliverables:

- Domain management.
- Document upload/mount management.
- Live job timeline for scan, OCR, extraction, segmentation, and indexing.
- Query workspace with provider/budget selection.
- Evidence and audit views.
- Settings/Admin views.

Exit criteria:

- A user can load a fixture corpus, index it, ask a question, and inspect evidence from the browser.

## Phase 5 - Evals

Deliverables:

- Local datasets.
- Deterministic scorers for retrieval, citation validity, grounding, abstention, and budget compliance.
- JSON/Markdown reports.
- Optional local LLM-as-judge profile.

Exit criteria:

- CI runs smoke evals without network or paid providers.

## Phase 6 - Alpha Release

Deliverables:

- Release images.
- Compose smoke test.
- Health checks.
- Documented config.
- Upgrade and backup notes.

Exit criteria:

- A user can run the stack locally and use Gemma 4 through Ollama.
