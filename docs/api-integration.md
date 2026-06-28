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

Admin bearer tokens are checked against the persisted `admin_users` row on each
management request. If an admin account is deactivated, existing tokens for that
account stop working.

## Admin Users

List local admin accounts:

```bash
curl --header "Authorization: Bearer <token>" \
  http://localhost:8000/admin/users
```

Create an admin account:

```bash
curl --request POST http://localhost:8000/admin/users \
  --header "Authorization: Bearer <token>" \
  --header "Content-Type: application/json" \
  --data '{"email":"ops@retos.dev","password":"change-me-with-12-plus-chars"}'
```

Activate or deactivate an account:

```bash
curl --request PATCH http://localhost:8000/admin/users/<admin_user_id>/status \
  --header "Authorization: Bearer <token>" \
  --header "Content-Type: application/json" \
  --data '{"is_active":false}'
```

Reset an admin password:

```bash
curl --request POST http://localhost:8000/admin/users/<admin_user_id>/password \
  --header "Authorization: Bearer <token>" \
  --header "Content-Type: application/json" \
  --data '{"password":"new-password-with-12-plus-chars"}'
```

The API never returns password hashes. It prevents self-deactivation, requires at
least one active admin, and writes `admin_user.created`,
`admin_user.status_updated`, and `admin_user.password_reset` journal events.

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

The React console uses these endpoints to populate the workspace selector, refresh
domain metrics, and create new research domains without requiring users to paste UUIDs.

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

Archived documents are hidden by default. Include them explicitly when auditing a
retired corpus item:

```bash
curl --header "Authorization: Bearer <token>" \
  "http://localhost:8000/domains/<domain_id>/documents?include_archived=true"
```

Read one document:

```bash
curl --header "Authorization: Bearer <token>" http://localhost:8000/documents/<document_id>
```

Update mutable document metadata:

```bash
curl --request PATCH http://localhost:8000/documents/<document_id> \
  --header "Authorization: Bearer <token>" \
  --header "Content-Type: application/json" \
  --data '{
    "title":"Reviewed Fixture Document",
    "metadata":{"language":"en","reviewed":true}
  }'
```

Archive a document without deleting its versions, artifacts, segments, or audit trail:

```bash
curl --request DELETE \
  --header "Authorization: Bearer <token>" \
  http://localhost:8000/documents/<document_id>
```

Restore an archived document to the active inventory:

```bash
curl --request POST \
  --header "Authorization: Bearer <token>" \
  http://localhost:8000/documents/<document_id>/restore
```

Read a chronological document history with auditable field-level changes:

```bash
curl --header "Authorization: Bearer <token>" \
  "http://localhost:8000/documents/<document_id>/history?limit=100"
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

Document title/metadata updates persist `document.updated` journal/progress events and
emit live SSE notifications. Archive operations set `archived_at`, persist
`document.archived` journal/progress events, emit SSE notifications, hide the document
from default lists, and exclude it from future BM25 rebuilds. The underlying versions,
artifacts, and segments remain available for audit and historical reads.
Restore operations clear `archived_at`, persist `document.restored` journal/progress
events, emit SSE notifications, and return the document to active lists and future index
rebuilds.
Document history reads the append-only journal for the document and surfaces `changes`
entries for title, metadata, archive, and restore events recorded after this contract was
introduced.

The console reads this list after a domain is selected and uses it as the visible
document inventory for the active research workspace.

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

## Text Ingestion

Queue plain-text ingestion for a domain:

```bash
curl --request POST http://localhost:8000/domains/<domain_id>/ingestions/text \
  --header "Authorization: Bearer <token>" \
  --header "Content-Type: application/json" \
  --data '{
    "source_id":"<source_id>",
    "title":"Fixture Text",
    "text":"The worker will hash, version, artifact, and segment this text.",
    "source_uri":"inline://fixture.txt",
    "metadata":{"language":"en"},
    "max_segment_tokens":220
  }'
```

The response is `202 Accepted` with a durable `ingest.source` job in `queued` status.
Outside `RETOS_ENV=test`, the API dispatches a Celery task to RabbitMQ. The worker then:

- transitions the job to `running`
- creates the canonical document and immutable version
- creates a `raw_text` artifact
- creates deterministic word-window segments
- transitions the job to `succeeded` or `failed`
- writes journal/progress records and SSE updates

Local API smoke runs with `RETOS_ENV=test`, so it verifies queuing without requiring a
broker. Docker smoke runs RabbitMQ and the worker and waits for the ingestion job to
finish.

## File Upload Ingestion

Queue an uploaded `.txt`, `.md`, or `.pdf` file for a domain:

```bash
curl --request POST http://localhost:8000/domains/<domain_id>/ingestions/upload \
  --header "Authorization: Bearer <token>" \
  --form "file=@./fixture-note.txt;type=text/plain" \
  --form "title=Fixture Upload" \
  --form "max_segment_tokens=220" \
  --form "enable_ocr=true" \
  --form "max_ocr_pages=20"
```

Optional fields:

- `source_id`: attaches the uploaded document to an existing source in the same domain.
- `title`: overrides the filename as the visible document title.
- `max_bytes`: defaults to 2 MB for the current product slice.
- `max_segment_tokens`: controls deterministic word-window chunking.
- `enable_ocr` and `max_ocr_pages`: allow local OCR fallback for image-only PDFs.

The API sanitizes the filename, rejects unsupported extensions before writing the file,
stores bytes under `RETOS_STORAGE_ROOT/uploads/<domain_id>/<upload_id>/`, creates a
durable `ingest.source` job, writes `upload.queued` journal/progress records, and emits
SSE progress. In Docker/runtime mode, RabbitMQ dispatches the job to the worker. The API
and worker use the same `retos-backend` image and the same storage volume, so the worker
processes the exact uploaded bytes instead of relying on a parallel implementation path.

When the worker succeeds, it creates the canonical document, immutable version,
text artifact (`raw_text`, `extracted_text`, or `ocr_text` depending on extraction),
deterministic segments, `document.ingested` journal event, `job.succeeded`
journal/progress records, and live `upload.completed` progress. Duplicate content hashes
in the same domain are rejected consistently with mounted scans and text ingestion.

## Mounted Source Scan

Scan a mounted `file://` source for `.txt`, `.md`, and digital `.pdf` files:

```bash
curl --request POST http://localhost:8000/sources/<source_id>/scan \
  --header "Authorization: Bearer <token>" \
  --header "Content-Type: application/json" \
  --data '{
    "run_inline":false,
    "max_files":500,
    "max_bytes":2000000,
    "max_segment_tokens":220,
    "enable_ocr":true,
    "max_ocr_pages":20
  }'
```

The source must have `kind="mount"` and a local `file://` URI that is visible to the API
or worker container. The scan creates one document/version/extracted-text artifact per new
file and deterministic word-window segments with anchors based on the relative path.
Existing content hashes in the same domain are skipped, so scanning the same corpus twice
is idempotent. PDFs first use local embedded-text extraction; when no text is available
and `enable_ocr=true`, pages are rendered locally and OCR is run through Tesseract.

In `RETOS_ENV=test`, or when `run_inline=true`, the scan runs inline. In Docker/runtime
mode, the scan is queued as an `ingest.source` job and processed by the worker.

## BM25 Search

Rebuild the local Tantivy BM25 projection for a domain:

```bash
curl --request POST http://localhost:8000/domains/<domain_id>/index/rebuild \
  --header "Authorization: Bearer <token>" \
  --header "Content-Type: application/json" \
  --data '{"run_inline":false}'
```

The response is a durable `index.domain` job. In `RETOS_ENV=test`, or when
`run_inline=true`, the rebuild happens in the request so integration tests do not need
RabbitMQ. In normal Docker/runtime mode, the API queues the job and the worker rebuilds
the index under `RETOS_INDEX_ROOT`.

Search a built index:

```bash
curl --header "Authorization: Bearer <token>" \
  "http://localhost:8000/domains/<domain_id>/search?q=search%20terms&limit=10"
```

Search hits include stable citation data:

```json
{
  "query": "search terms",
  "hits": [
    {
      "segment_id": "<segment_id>",
      "document_id": "<document_id>",
      "document_version_id": "<version_id>",
      "title": "Fixture Document",
      "text": "Matching segment text",
      "anchor": "page=1",
      "ordinal": 0,
      "score": 1.23
    }
  ]
}
```

If the index has not been built, search returns `409 Conflict`.

## Agent Queries

Agent queries are durable jobs that use indexed evidence and return citation-backed
answers. The current implementation runs the safe RetOS research harness path for
`fake`/`local` profiles without paid provider calls.

```bash
curl --request POST http://localhost:8000/domains/<domain_id>/queries \
  --header "Authorization: Bearer <token>" \
  --header "Content-Type: application/json" \
  --data '{
    "question":"What evidence mentions search readiness?",
    "limit":5,
    "run_inline":true
  }'
```

The response always includes the durable job. When `run_inline=true`, or in
`RETOS_ENV=test`, it also includes the result:

```json
{
  "job": {
    "id": "<job_id>",
    "kind": "agent.query",
    "status": "succeeded"
  },
  "result": {
    "answer": "Grounded answer for: ...",
    "provider": "local",
    "model": "ollama:gemma4",
    "citations": [
      {
        "segment_id": "<segment_id>",
        "document_id": "<document_id>",
        "document_version_id": "<version_id>",
        "title": "Fixture Document",
        "anchor": "page=1",
        "score": 1.23,
        "text": "Matching evidence text"
      }
    ]
  }
}
```

In Docker/runtime mode, omit `run_inline` to queue the job for the worker. The worker
stores the final result under `job.payload.result`, writes `agent.*` journal/progress
events, and emits SSE progress. If the domain index has not been built, the API returns
`409 Conflict` and marks the job failed.

## LLM Providers

Provider discovery is admin-only and safe to call from the UI. It does not return API
keys and does not perform paid model calls.

```bash
curl --request GET http://localhost:8000/llm/providers \
  --header "Authorization: Bearer <token>"
```

The response includes the active profile and the available profiles:

```json
{
  "active": {
    "provider": "local",
    "model": "ollama:gemma4",
    "paid": false,
    "can_call": true,
    "reason": null
  },
  "providers": [
    {
      "name": "local",
      "label": "Ollama local runtime",
      "default_model": "gemma4",
      "configured": true,
      "enabled": true,
      "paid": false,
      "reason": null,
      "base_url": "http://ollama:11434/"
    }
  ]
}
```

`fake` is reserved for tests. `openai`, `anthropic`, `google`, `openrouter`, and
`azure` require their provider-specific key/configuration and remain disabled unless
`RETOS_ALLOW_PAID_LLM=true`.

## Evals

Run the deterministic local smoke eval suite:

```bash
curl --request POST http://localhost:8000/evals/smoke \
  --header "Authorization: Bearer <token>"
```

The endpoint requires an admin token, does not call paid providers, and returns
`202 Accepted` with a durable `eval.run` job plus the report:

```json
{
  "job": {
    "id": "<job_id>",
    "kind": "eval.run",
    "status": "succeeded"
  },
  "report": {
    "suite_name": "retos-smoke",
    "passed": true,
    "case_count": 3,
    "metrics": {
      "retrieval_recall": 1.0,
      "citation_validity": 1.0,
      "grounded_answer": 1.0,
      "abstention": 1.0,
      "budget_compliance": 1.0
    },
    "cases": [
      {
        "case_id": "apollo-guidance",
        "passed": true,
        "failures": []
      }
    ]
  }
}
```

The run writes:

- an `eval.run` job with the report under `job.payload.result`
- `eval.queued`, `eval.started`, and `eval.completed` progress events
- `eval.queued`, `job.running`, `eval.completed`, and `job.succeeded` journal events
- live SSE progress events for connected clients

Run an opt-in SQuAD 2.0 eval from a mounted local dataset file:

```bash
curl --request POST http://localhost:8000/evals/squad \
  --header "Authorization: Bearer <token>" \
  --header "Content-Type: application/json" \
  --data '{
    "dataset_path":"dev-v2.0.json",
    "max_cases":50,
    "write_report":true,
    "report_stem":"squad-v2-dev-50"
  }'
```

The request uses the same response shape as `/evals/smoke` and adds `report_paths`
when filesystem export is enabled:

```json
{
  "job": {
    "id": "<job_id>",
    "kind": "eval.run",
    "status": "succeeded"
  },
  "report": {
    "suite_name": "squad-v2",
    "passed": true,
    "case_count": 50
  },
  "report_paths": {
    "json": "/var/lib/retos/evals/reports/squad-v2-dev-50.json",
    "markdown": "/var/lib/retos/evals/reports/squad-v2-dev-50.md"
  }
}
```

Security and runtime notes:

- `dataset_path` must resolve inside `RETOS_EVAL_DATASET_ROOT`; traversal and
  absolute paths outside that root return `422`.
- Missing dataset files return `404` before any job is created.
- Adapter or schema errors return `422` and mark the created eval job failed.
- Reports are written under `RETOS_EVAL_REPORT_ROOT`; clients receive paths for
  later audit/export workflows.
- API smoke creates a tiny SQuAD fixture and verifies this endpoint over HTTP.

List recent persisted eval runs:

```bash
curl "http://localhost:8000/evals/runs?limit=6" \
  --header "Authorization: Bearer <token>"
```

The response is ordered newest-first and includes runs that failed before a report
was produced:

```json
[
  {
    "job": {
      "id": "<job_id>",
      "kind": "eval.run",
      "status": "succeeded"
    },
    "report": {
      "suite_name": "retos-smoke",
      "passed": true,
      "case_count": 3
    }
  }
]
```

Compare two persisted eval runs:

```bash
curl "http://localhost:8000/evals/runs/compare?baseline_job_id=<old_job_id>&candidate_job_id=<new_job_id>" \
  --header "Authorization: Bearer <token>"
```

The endpoint reads reports already stored in `job.payload.result`, does not call
providers, and returns per-metric deltas:

```json
{
  "baseline": {
    "job_id": "<old_job_id>",
    "suite_name": "retos-smoke",
    "passed": true,
    "case_count": 3
  },
  "candidate": {
    "job_id": "<new_job_id>",
    "suite_name": "squad-v2",
    "passed": true,
    "case_count": 2
  },
  "metrics": [
    {
      "name": "retrieval_recall",
      "baseline": 1.0,
      "candidate": 1.0,
      "delta": 0.0
    }
  ],
  "average_delta": 0.0,
  "status": "unchanged"
}
```

### Frontend Runtime Notes

The React console reads `VITE_RETOS_API_URL` and falls back to `http://localhost:8000`.
The provider panel authenticates with `/auth/login`, stores the admin bearer token in
browser local storage under `retos.adminToken`, and then calls `/llm/providers` and
the workspace endpoints.

Current console calls:

- `POST /auth/login`
- `GET /admin/users`
- `POST /admin/users`
- `PATCH /admin/users/{admin_user_id}/status`
- `POST /admin/users/{admin_user_id}/password`
- `GET /llm/providers`
- `GET /domains`
- `POST /domains`
- `GET /domains/{domain_id}/documents`
- `PATCH /documents/{document_id}`
- `DELETE /documents/{document_id}`
- `POST /documents/{document_id}/restore`
- `GET /documents/{document_id}/history`
- `GET /domains/{domain_id}/sources`
- `POST /domains/{domain_id}/sources`
- `POST /domains/{domain_id}/ingestions/text`
- `POST /domains/{domain_id}/ingestions/upload`
- `POST /sources/{source_id}/scan`
- `POST /domains/{domain_id}/index/rebuild`
- `POST /domains/{domain_id}/queries`
- `GET /evals/runs?limit=6`
- `GET /evals/runs/compare?baseline_job_id=...&candidate_job_id=...`
- `POST /evals/smoke`
- `POST /evals/squad`
- `GET /jobs?limit=12`
- `GET /audit/journal-events?limit=20`
- `GET /audit/progress-events?limit=20`

The UI treats the provider catalog as read-only operational status and admin users as
audited local accounts:

- `active.can_call=true` means the selected profile is ready to call.
- `paid=true` means the UI must show a cost warning before future query execution.
- `enabled=false` plus `reason` explains whether configuration or cost opt-in is missing.
- API keys are never returned to the browser.
- Admin passwords are write-only; the browser can create accounts and submit resets,
  but only receives account metadata and active/inactive state.

The workspace can create domains, select an active domain, render its document and source
inventory, create mounted sources, queue text and file upload ingestions, queue source
scans, rebuild the BM25 index, run local smoke/SQuAD evals, read recent jobs, read
persisted audit/progress events, filter the job ledger by status/kind, and send queries
against the selected domain. Query execution uses `run_inline=true` so the UI can render
the answer and citations immediately.
Worker-backed query jobs are already available through the API by omitting `run_inline`;
the live progress panel reads the same SSE stream that ingestion, indexing, and agent
jobs write to.

## Audit Events

Recent journal events:

```bash
curl --header "Authorization: Bearer <token>" \
  "http://localhost:8000/audit/journal-events?limit=20"
```

Recent persisted progress events:

```bash
curl --header "Authorization: Bearer <token>" \
  "http://localhost:8000/audit/progress-events?limit=20"
```

Export a combined audit snapshot:

```bash
curl --header "Authorization: Bearer <token>" \
  --output retos-audit-export.json \
  "http://localhost:8000/audit/export?limit=200"
```

Both endpoints require an admin token and accept `limit` from `1` to `200`. Results are
ordered newest first.

The export endpoint requires an admin token, accepts `limit` from `1` to `1000`, returns
`Content-Disposition: attachment; filename="retos-audit-export.json"`, and sets
`Cache-Control: no-store`.

Journal event shape:

```json
{
  "id": "<event_id>",
  "occurred_at": "2026-06-27T00:00:00Z",
  "actor": "admin@retos.dev",
  "event_type": "job.created",
  "entity_type": "job",
  "entity_id": "<job_id>",
  "payload": {
    "kind": "index.domain",
    "status": "queued"
  }
}
```

Progress event shape:

```json
{
  "id": "<event_id>",
  "job_id": "<job_id>",
  "occurred_at": "2026-06-27T00:00:00Z",
  "event_type": "job.queued",
  "message": "Queued index.domain",
  "payload": {
    "status": "queued"
  }
}
```

Audit export shape:

```json
{
  "schema_version": "retos.audit-export.v1",
  "generated_at": "2026-06-27T00:00:00Z",
  "limit": 200,
  "journal_events": [],
  "progress_events": []
}
```

The React audit panel uses these endpoints to show durable journal/progress evidence next
to the job ledger and to download a JSON audit export without putting bearer tokens in
URLs. SSE remains the live stream; `/audit/*` is the reloadable persisted record.

## Progress Events

Long-running workflows expose progress through Server-Sent Events:

```bash
curl --no-buffer \
  --header "Authorization: Bearer <token>" \
  http://localhost:8000/events/progress
```

The browser should reconnect with `Last-Event-ID` when a connection drops.

Because the progress stream is authenticated, the React console consumes it with
`fetch()` and a readable stream so it can send the bearer token. Browser `EventSource`
does not support custom authorization headers. The UI keeps the latest progress events
in a compact ledger and reserves space for empty, connected, and error states.

SSE ids are stable cursors:

- `progress:<progress_event_id>` is backed by the persisted `progress_events` table and
  can resume after API restarts.
- `live:<number>` is an in-memory notification cursor for process-local events.

On connect, the API replays recent persisted progress events before live memory events.
When `Last-Event-ID` is a `progress:*` cursor, the replay starts after that persisted
row. The React console tracks the latest `progress:*` id separately and sends it on the
next authenticated fetch reconnect.

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
