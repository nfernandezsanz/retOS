# Database And Migrations

RetOS treats Postgres as the durable catalog for domains, sources, documents, document
versions, artifacts, jobs, progress events, and audit journals. Search indexes and local
files are rebuildable projections; the database schema is the auditable contract.

## Migration Tooling

Alembic lives under `backend/alembic/` and uses the async SQLAlchemy drivers already
installed by the backend runtime. The same configuration supports local SQLite test
databases and the Docker Postgres service.

Run migrations locally:

```bash
make db-upgrade
```

Roll back the latest revision:

```bash
make db-downgrade
```

When running through Docker Compose, the `migrate` service applies `alembic upgrade head`
before the API and worker start. It uses the same `retos-backend` image as both backend
roles, so migrations are tested against the exact runtime package.

## Initial Schema

The first revision creates these tables:

| Table | Purpose |
| --- | --- |
| `admin_users` | Persisted admin identities used by login and bootstrap. |
| `domains` | User-managed research workspaces. |
| `sources` | Upload, mounted path, or URL inputs attached to a domain. |
| `documents` | Canonical document records keyed by domain and content hash. |
| `document_versions` | Immutable versions of document bytes or extracted content. |
| `artifacts` | Derived files such as raw text, OCR output, page images, or manifests. |
| `segments` | Searchable chunks with anchors and token counts. |
| `jobs` | Durable long-running work records for ingestion, indexing, evals, and agents. |
| `progress_events` | Persisted progress updates that can back SSE streams and UI timelines. |
| `journal_events` | Append-only audit facts for user and system actions. |

The first API-backed workflows are document registration and job creation:

- Application startup bootstraps `RETOS_BOOTSTRAP_ADMIN_EMAIL` into `admin_users`
  when it is configured and no user exists yet for that email.
- `POST /domains/{domain_id}/documents` creates a document, writes version `1`,
  writes `document.created` journal/progress events, and emits a live SSE notification.
- `PATCH /documents/{document_id}` updates mutable document title/metadata fields,
  writes `document.updated` journal/progress events, and emits a live SSE notification.
- `DELETE /documents/{document_id}` soft-archives the document by setting `archived_at`,
  writes `document.archived` journal/progress events, and emits a live SSE notification.
  Default document lists and BM25 rebuilds ignore archived documents; historical reads can
  still include them for audit.
- `POST /documents/{document_id}/restore` clears `archived_at`, writes
  `document.restored` journal/progress events, emits a live SSE notification, and returns
  the document to active lists and future index rebuilds.
- `GET /documents/{document_id}/history` reads the document's append-only journal events
  and returns chronological field-level changes for title, metadata, archive, and restore
  events that include diff payloads.
- `POST /document-versions/{version_id}/artifacts` creates a rebuildable artifact and
  writes `artifact.created` journal/progress events.
- `POST /document-versions/{version_id}/segments` creates a searchable/citable segment and
  writes `segment.created` journal/progress events.
- `POST /jobs` creates a queued job, writes a `job.created` journal event, writes a
  `job.queued` progress event, and emits a live SSE notification.
- `POST /jobs/{job_id}/start|complete|fail|cancel` changes durable job status and
  writes journal/progress/SSE events for every transition.
- `POST /domains/{domain_id}/ingestions/text` queues an `ingest.source` job. The Celery
  worker materializes the text as a document, initial version, `raw_text` artifact, and
  deterministic segments, then writes `document.ingested`, `job.succeeded` or `job.failed`,
  and ingestion progress events.
- `POST /domains/{domain_id}/ingestions/upload` stores sanitized `.txt`, `.md`, or `.pdf`
  uploads in shared storage, queues an `ingest.source` job, and lets the worker create the
  canonical document/version, `extracted_text` artifact, deterministic segments, and
  upload-specific journal/progress events.
- `POST /sources/{source_id}/scan` queues an `ingest.source` job for mounted `file://`
  `.txt`, `.md`, and digital `.pdf` corpora. The scan skips duplicate domain content
  hashes, preserving idempotency for repeated fixture corpus runs.
- `POST /domains/{domain_id}/index/rebuild` queues an `index.domain` job. The worker reads
  persisted segments and rebuilds a Tantivy BM25 projection under `RETOS_INDEX_ROOT`. The
  index remains disposable; persisted segments and document metadata are the canonical
  source.

## Development Contract

- ORM metadata and Alembic revisions must stay in sync.
- New tables and constraints require migration tests.
- Runtime containers must never rely on `metadata.create_all` for production paths.
- Tests may use SQLite for fast contract checks, but Docker smoke validates Postgres
  wiring through the real Compose stack.
- Paid LLM providers must not be needed to create, migrate, or test the schema.
