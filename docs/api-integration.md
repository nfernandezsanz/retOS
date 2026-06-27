# API Integration Guide

This guide documents the stable integration surface currently available to the React console, browser smoke tests, and external clients.

## Authentication

All management endpoints require an admin bearer token. The default local admin is
persisted in `admin_users` during application startup when the bootstrap environment
variables are configured.

```bash
curl --request POST http://localhost:8000/auth/login \
  --header "Content-Type: application/json" \
  --data '{"email":"admin@retos.dev","password":"retos-dev-admin-change-me"}'
```

Use the returned token as:

```http
Authorization: Bearer <token>
```

## Domains

Create a domain:

```bash
curl --request POST http://localhost:8000/domains \
  --header "Authorization: Bearer <token>" \
  --header "Content-Type: application/json" \
  --data '{"slug":"research","name":"Research","description":"Fixture corpus"}'
```

List domains:

```bash
curl --header "Authorization: Bearer <token>" http://localhost:8000/domains
```

Read a domain:

```bash
curl --header "Authorization: Bearer <token>" http://localhost:8000/domains/<domain_id>
```

## Sources

Create a source for a domain:

```bash
curl --request POST http://localhost:8000/domains/<domain_id>/sources \
  --header "Authorization: Bearer <token>" \
  --header "Content-Type: application/json" \
  --data '{"kind":"mount","name":"Research corpus","uri":"file:///corpus/research"}'
```

Valid `kind` values are `upload`, `mount`, and `url`.

List sources:

```bash
curl --header "Authorization: Bearer <token>" \
  http://localhost:8000/domains/<domain_id>/sources
```

## Documents

Create a document with its immutable initial version:

```bash
curl --request POST http://localhost:8000/domains/<domain_id>/documents \
  --header "Authorization: Bearer <token>" \
  --header "Content-Type: application/json" \
  --data '{
    "source_id":"<source_id>",
    "external_id":"fixture-001",
    "title":"Fixture Document",
    "content_hash":"sha256:abc12345",
    "source_uri":"upload://fixture-001.txt",
    "size_bytes":128,
    "metadata":{"language":"en"}
  }'
```

`content_hash` accepts raw hex or `sha256:<hex>`. Hashes are unique per domain.

List documents for a domain:

```bash
curl --header "Authorization: Bearer <token>" \
  "http://localhost:8000/domains/<domain_id>/documents?limit=100"
```

Read one document:

```bash
curl --header "Authorization: Bearer <token>" http://localhost:8000/documents/<document_id>
```

List immutable versions:

```bash
curl --header "Authorization: Bearer <token>" \
  http://localhost:8000/documents/<document_id>/versions
```

Document creation persists:

- a row in `documents`
- version `1` in `document_versions`
- a `document.created` journal event
- a `document.created` progress event
- a live SSE notification for connected clients

## Artifacts

Artifacts are derived files for a document version: raw text, OCR text, page images,
manifests, or other rebuildable outputs.

Create an artifact:

```bash
curl --request POST http://localhost:8000/document-versions/<version_id>/artifacts \
  --header "Authorization: Bearer <token>" \
  --header "Content-Type: application/json" \
  --data '{
    "kind":"raw_text",
    "uri":"storage://documents/fixture/raw.txt",
    "sha256":"sha256:11111111",
    "size_bytes":64
  }'
```

List artifacts:

```bash
curl --header "Authorization: Bearer <token>" \
  http://localhost:8000/document-versions/<version_id>/artifacts
```

Artifacts are unique per `(document_version_id, kind, uri)`.

## Segments

Segments are searchable chunks for BM25/vector retrieval and citation anchoring.

Create a segment:

```bash
curl --request POST http://localhost:8000/document-versions/<version_id>/segments \
  --header "Authorization: Bearer <token>" \
  --header "Content-Type: application/json" \
  --data '{
    "ordinal":0,
    "text":"This is a searchable fixture segment.",
    "anchor":"page=1",
    "token_count":7,
    "content_hash":"sha256:22222222"
  }'
```

List segments:

```bash
curl --header "Authorization: Bearer <token>" \
  http://localhost:8000/document-versions/<version_id>/segments
```

Segments are ordered by `ordinal` and are unique per document version.

## Progress Events

Long-running workflows expose progress through Server-Sent Events:

```bash
curl --no-buffer \
  --header "Authorization: Bearer <token>" \
  http://localhost:8000/events/progress
```

The browser should reconnect with `Last-Event-ID` when a connection drops.

## Jobs

Create a durable job:

```bash
curl --request POST http://localhost:8000/jobs \
  --header "Authorization: Bearer <token>" \
  --header "Content-Type: application/json" \
  --data '{
    "kind":"ingest.source",
    "domain_id":"<domain_id>",
    "source_id":"<source_id>",
    "payload":{"reason":"manual-ingest"}
  }'
```

Valid `kind` values are:

| Kind | Purpose |
| --- | --- |
| `ingest.source` | Scan/hash/extract documents from a source. |
| `index.domain` | Rebuild searchable projections for a domain. |
| `eval.run` | Run local evaluation suites. |
| `agent.query` | Execute an auditable research query. |

New jobs start as `queued`. Job creation persists:

- a row in `jobs`
- a `job.created` journal event
- a `job.queued` progress event
- a live SSE notification for connected clients

Transition jobs through the durable lifecycle:

```bash
curl --request POST --header "Authorization: Bearer <token>" \
  http://localhost:8000/jobs/<job_id>/start

curl --request POST --header "Authorization: Bearer <token>" \
  http://localhost:8000/jobs/<job_id>/complete

curl --request POST http://localhost:8000/jobs/<job_id>/fail \
  --header "Authorization: Bearer <token>" \
  --header "Content-Type: application/json" \
  --data '{"error":"OCR failed"}'

curl --request POST --header "Authorization: Bearer <token>" \
  http://localhost:8000/jobs/<job_id>/cancel
```

Allowed transitions:

| From | To |
| --- | --- |
| `queued` | `running`, `cancelled` |
| `running` | `succeeded`, `failed`, `cancelled` |
| `succeeded` | terminal |
| `failed` | terminal |
| `cancelled` | terminal |

Each transition writes a journal event, a progress event, and a live SSE update.

List jobs:

```bash
curl --header "Authorization: Bearer <token>" \
  "http://localhost:8000/jobs?limit=100"
```

Read one job:

```bash
curl --header "Authorization: Bearer <token>" http://localhost:8000/jobs/<job_id>
```

## Persistence Notes

The API is wired through a SQLAlchemy async Unit of Work. Tests and smoke checks use SQLite with `RETOS_DATABASE_CREATE_ALL=true`. Production-like deployments should use Postgres and managed migrations. Login reads persisted `admin_users`; bootstrap settings only create the initial account idempotently.
