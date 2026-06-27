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
| `domains` | User-managed research workspaces. |
| `sources` | Upload, mounted path, or URL inputs attached to a domain. |
| `documents` | Canonical document records keyed by domain and content hash. |
| `document_versions` | Immutable versions of document bytes or extracted content. |
| `artifacts` | Derived files such as raw text, OCR output, page images, or manifests. |
| `segments` | Searchable chunks with anchors and token counts. |
| `jobs` | Durable long-running work records for ingestion, indexing, evals, and agents. |
| `progress_events` | Persisted progress updates that can back SSE streams and UI timelines. |
| `journal_events` | Append-only audit facts for user and system actions. |

## Development Contract

- ORM metadata and Alembic revisions must stay in sync.
- New tables and constraints require migration tests.
- Runtime containers must never rely on `metadata.create_all` for production paths.
- Tests may use SQLite for fast contract checks, but Docker smoke validates Postgres
  wiring through the real Compose stack.
- Paid LLM providers must not be needed to create, migrate, or test the schema.
