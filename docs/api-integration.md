# API Integration Guide

This guide documents the stable integration surface currently available to the React console, browser smoke tests, and external clients.

## Health And Readiness

`GET /healthz` is the cheap liveness check. It returns `{"status":"ok","service":"retos-api"}`
without touching downstream dependencies.

`GET /readyz` is the Docker/operator readiness check. It validates a lightweight database
round trip and returns component status:

```json
{
  "status": "ok",
  "service": "retos-api",
  "components": {
    "database": "ok"
  }
}
```

If the database cannot be reached, `/readyz` returns `503` with
`components.database="unavailable"`. Neither endpoint requires authentication and neither
returns secrets.

`GET /versionz` exposes the runtime build metadata operators need to match a running
container with its image labels and release evidence:

```json
{
  "service": "retos-api",
  "version": "local",
  "revision": "unknown",
  "created": "unknown"
}
```

The values come from `RETOS_VERSION`, `RETOS_REVISION`, and `RETOS_CREATED`.
The endpoint is intentionally unauthenticated and must never include secrets.

## Authentication And Authorization

Operational endpoints require a bearer token from a persisted local account. The default
local admin is persisted in `admin_users` during application startup when the bootstrap
environment variables are configured. `RETOS_BOOTSTRAP_ADMIN_PASSWORD` follows the same
minimum length policy as managed admin passwords and must contain at least 12 characters.

```bash
curl --request POST http://localhost:8000/auth/login \
  --header "Content-Type: application/json" \
  --data '{"email":"admin@retos.dev","password":"retos-dev-admin-change-me"}'
```

Use the returned token as:

```http
Authorization: Bearer <token>
```

Bearer tokens are checked against the persisted `admin_users` row on each protected
request. If an account is deactivated or its persisted roles no longer cover the token
roles, existing tokens for that account stop working.

Roles are intentionally small:

| Role | Allowed |
| --- | --- |
| `admin` | Full local administration: account management, domain/source/document mutations, ingestion, indexing, agent queries, eval execution, job transitions, job retry, and all read-only operations. |
| `viewer` | Read-only operational visibility. Domain-scoped resources, audit journal/progress/export, persisted SSE replay, and dataset-backed eval execution/history/trends/reruns/comparison/regression gates require explicit domain grants plus `domain_id`. Provider catalog remains a global observability surface because it exposes readiness, not secrets. Global evals and built-in evals require an admin token. |

Endpoints that mutate state, spend compute, enqueue work, or change account security
require an `admin` token. Viewer-safe endpoints use the same `Authorization` header but
accept either an `admin` or `viewer` token. Domain-scoped viewer access is granted per
domain by an admin; without a grant, viewers receive `403 Domain access required`.

## Local Demo Corpus

Seed the bundled local corpus from the UI or API:

```bash
curl --request POST http://localhost:8000/demo/seed \
  --header "Authorization: Bearer <token>" \
  --header "Content-Type: application/json" \
  --data '{"rebuild_index":true}'
```

The endpoint requires an `admin` token and returns the created or reused domain/source
identifiers plus created/skipped document counts and indexed segment count. It runs the
same auditable text-ingestion and BM25 rebuild services as normal document workflows,
so journal and progress hash-chain events are preserved. RetOS rejects this endpoint in
production mode.

## Admin Users

List local admin accounts:

```bash
curl --header "Authorization: Bearer <token>" \
  http://localhost:8000/admin/users
```

Create an admin account. `roles` defaults to `["admin"]`; supported values are `admin`
and `viewer`.

```bash
curl --request POST http://localhost:8000/admin/users \
  --header "Authorization: Bearer <token>" \
  --header "Content-Type: application/json" \
  --data '{"email":"ops@retos.dev","password":"change-me-with-12-plus-chars","roles":["admin"]}'
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

Update account roles:

```bash
curl --request PATCH http://localhost:8000/admin/users/<admin_user_id>/roles \
  --header "Authorization: Bearer <token>" \
  --header "Content-Type: application/json" \
  --data '{"roles":["viewer"]}'
```

The API never returns password hashes. It prevents self-deactivation, prevents removing
your own `admin` role, requires at least one active admin role, and writes
`admin_user.created`, `admin_user.status_updated`, `admin_user.roles_updated`, and
`admin_user.password_reset` journal events.

Grant a viewer access to a domain:

```bash
curl --request POST http://localhost:8000/admin/users/<admin_user_id>/domain-grants \
  --header "Authorization: Bearer <token>" \
  --header "Content-Type: application/json" \
  --data '{"domain_id":"<domain_id>"}'
```

List or revoke grants:

```bash
curl --header "Authorization: Bearer <token>" \
  http://localhost:8000/admin/users/<admin_user_id>/domain-grants

curl --request DELETE \
  --header "Authorization: Bearer <token>" \
  http://localhost:8000/admin/users/<admin_user_id>/domain-grants/<domain_id>
```

Domain grant changes write `admin_user.domain_grant_created` and
`admin_user.domain_grant_deleted` journal events. Admin users do not need grants; they
always have full local access.

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

Archived domains are hidden by default. Include them explicitly when reviewing or
restoring old workspaces:

```bash
curl --header "Authorization: Bearer <token>" \
  "http://localhost:8000/domains?include_archived=true"
```

Read a domain:

```bash
curl --header "Authorization: Bearer <token>" http://localhost:8000/domains/<domain_id>
```

Update a domain's operator-facing details. The slug stays immutable; name and description
changes write a `domain.updated` journal event with field-level before/after values:

```bash
curl --request PATCH http://localhost:8000/domains/<domain_id> \
  --header "Authorization: Bearer <token>" \
  --header "Content-Type: application/json" \
  --data '{"name":"Research Review","description":"Updated corpus boundary"}'
```

Archive a domain without deleting its sources, documents, jobs, grants, or audit history.
The endpoint writes a `domain.archived` journal event and sets `archived_at`:

```bash
curl --request DELETE http://localhost:8000/domains/<domain_id> \
  --header "Authorization: Bearer <token>"
```

Restore an archived domain. The endpoint writes a `domain.restored` journal event and
clears `archived_at`:

```bash
curl --request POST http://localhost:8000/domains/<domain_id>/restore \
  --header "Authorization: Bearer <token>"
```

The React console uses these endpoints to populate the workspace selector, refresh
domain metrics, create new research domains, edit active domain details, and archive or
restore domains without requiring users to paste UUIDs.

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

Update a source's operator-facing details. The source remains attached to the same
domain; kind, name, and URI changes write a `source.updated` journal event with
field-level before/after values:

```bash
curl --request PATCH http://localhost:8000/domains/<domain_id>/sources/<source_id> \
  --header "Authorization: Bearer <token>" \
  --header "Content-Type: application/json" \
  --data '{"kind":"mount","name":"Reviewed corpus","uri":"file:///corpus/reviewed"}'
```

Remove a source from a domain without deleting already-ingested documents. Existing
documents and jobs keep their audit history and are detached from the removed source.
The endpoint writes a `source.deleted` journal event with a snapshot of the removed
source kind, name, and URI:

```bash
curl --request DELETE http://localhost:8000/domains/<domain_id>/sources/<source_id> \
  --header "Authorization: Bearer <token>"
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

Artifacts are derived files for a document version: raw text, OCR text, page-level OCR
text, page images, manifests, or other rebuildable outputs.

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

Artifacts are unique per `(document_version_id, kind, uri)`. OCR fallback creates one
aggregate `ocr_text` artifact for the source URI and one `ocr_page_text` artifact per
successfully OCR'd page using `#page=N` URI anchors. The page artifacts make OCR output
auditable without changing the canonical document/version schema.

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
and rejects declared MIME types that conflict with the extension. Generic or missing
types are accepted for local tooling compatibility, but explicit pairs must match:

| Extension | Accepted declared content types |
| --- | --- |
| `.txt` | `text/plain`, `application/octet-stream` |
| `.md` | `text/markdown`, `text/x-markdown`, `text/plain`, `application/octet-stream` |
| `.pdf` | `application/pdf`, `application/x-pdf`, `application/octet-stream` |

Accepted uploads are stored under
`RETOS_STORAGE_ROOT/uploads/<domain_id>/<upload_id>/`, create a durable
`ingest.source` job, record the declared `content_type` in the job payload and
document ingestion metadata, write `upload.queued` journal/progress records, and emit
SSE progress. In Docker/runtime mode, RabbitMQ dispatches the job to the worker. The
API and worker use the same `retos-backend` image and the same storage volume, so the
worker processes the exact uploaded bytes instead of relying on a parallel
implementation path.

When the worker succeeds, it creates the canonical document, immutable version,
text artifact (`raw_text`, `extracted_text`, or `ocr_text` depending on extraction),
page-level `ocr_page_text` artifacts when OCR fallback is used, deterministic segments,
`document.ingested` journal event, `job.succeeded` journal/progress records, and live
`upload.completed` progress. Duplicate content hashes in the same domain are rejected
consistently with mounted scans and text ingestion.

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
and `enable_ocr=true`, pages are rendered locally and OCR is run through Tesseract. OCR
fallback writes an aggregate `ocr_text` artifact plus per-page `ocr_page_text` artifacts
with stable `#page=N` URI anchors.

In `RETOS_ENV=test`, or when `run_inline=true`, the scan runs inline. In Docker/runtime
mode, the scan is queued as an `ingest.source` job and processed by the worker.

## BM25 Search

For a fast local demo corpus, seed the running Docker stack:

```bash
make docker-seed-demo
```

The command creates or reuses the `retos-demo` domain, queues normal text-ingestion
jobs for three local fixture documents, runs the same ingestion service used by workers,
records journal/progress hash-chain events, rebuilds the local BM25 projection, and can
be repeated safely. Search examples that should return hits after seeding include
`Apollo guidance`, `plankton salinity`, and `incident retention`.

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
    "run_inline":true,
    "budget":{
      "max_searches":8,
      "max_citations":5,
      "max_evidence_tokens":16000,
      "max_runtime_seconds":120
    }
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
    "runtime": "deterministic",
    "evidence_audit": {
      "grounded": true,
      "cited_segment_ids": ["<segment_id>"],
      "unreferenced_citation_ids": []
    },
    "contradiction_audit": {
      "checked": true,
      "conflict_count": 0,
      "findings": []
    },
    "multi_hop_audit": {
      "checked": true,
      "requires_multi_hop": false,
      "status": "not_required",
      "document_count": 1,
      "bridge_terms": [],
      "warnings": []
    },
    "query_plan": {
      "strategy": "direct_evidence_lookup",
      "requires_multi_hop": false,
      "search_queries": ["What evidence mentions search readiness?"],
      "expected_evidence": "single_document_or_abstain",
      "warnings": [],
      "steps": [
        {
          "name": "search",
          "description": "Run bounded BM25 search over the selected domain.",
          "status": "planned"
        },
        {
          "name": "read",
          "description": "Read only citations returned by controlled corpus search.",
          "status": "planned"
        }
      ]
    },
    "evidence_route": {
      "coverage_level": "single_segment",
      "segment_count": 1,
      "document_count": 1,
      "anchor_count": 1,
      "multi_document": false,
      "has_neighbor_context": true,
      "warnings": ["single_citation", "single_document"],
      "documents": [
        {
          "document_id": "<document_id>",
          "title": "Fixture Document",
          "segment_ids": ["<segment_id>"],
          "anchors": ["page=1"]
        }
      ]
    },
    "usage": {
      "budget": {
        "max_searches": 8,
        "max_citations": 5,
        "max_evidence_tokens": 16000,
        "max_runtime_seconds": 120
      },
      "search_count": 1,
      "citation_count": 1,
      "evidence_tokens": 6,
      "runtime_ms": 24,
      "within_budget": true
    },
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

Agent budgets are persisted in the queued job payload and echoed in the final result
usage. The runtime always uses controlled RetOS corpus tools instead of host filesystem
access: `search_corpus` performs bounded BM25 searches, `read_citation` can read only
citations returned by those searches, `map_sources` groups already-selected evidence by
document/anchor, and `inspect_evidence_table` extracts simple table/key-value rows from
already-selected evidence. The runtime caps citations with `max_citations`, caps
retained evidence with `max_evidence_tokens`, and records `search_count`,
`citation_count`, `evidence_tokens`, `runtime_ms`, and `within_budget` for audit and UI
display.

Every completed query also persists `evidence_audit`. If citations exist but the answer
does not reference returned segment ids, RetOS appends an `Evidence ledger` to the final
answer and records which citation ids are now linked. This keeps Deep Agents output
auditable without granting the model host filesystem access.

The `contradiction_audit` is a deterministic first-pass reviewer over returned
citations. It flags citation pairs with opposite polarity markers and overlapping
domain terms so operators can review conflicting evidence. It is intentionally
conservative and does not replace deeper named subagent review.

The `multi_hop_audit` is a deterministic review of cross-document evidence. It marks
questions with simple multi-hop indicators such as `compare`, `between`, `both`, `same`,
or `and`, records whether the selected citations span multiple documents, extracts shared
bridge terms across cited documents, and emits warnings such as
`multi_hop_question_single_document` or `missing_cross_document_bridge_terms`. It gives
operators a cheap way to see whether a multi-part question was answered from broad enough
evidence before relying on the final answer.

The `query_plan` is generated before synthesis and persisted with the completed query.
It records the deterministic strategy, whether multi-hop evidence is expected, bounded
search queries, planned search/read/route/audit steps, and specificity warnings. Direct
queries run the initial bounded search only. Multi-hop plans execute distinct planned
subqueries until `max_searches` is reached, deduplicate citation candidates, and keep the
final selected evidence within citation and token budgets. The same plan and executed
`planned_searches` are included in the Deep Agents seed payload so local and agentic
runtimes share the same auditable intent.

The `evidence_route` is a deterministic coverage map for the answer. It records the
coverage level (`no_evidence`, `single_segment`, `single_document`, or
`multi_document`), citation segment count, document count, anchor count, per-document
segment ids and anchors, whether adjacent context was expanded, and operator warnings
such as `single_citation`, `single_document`, or `no_neighbor_context`. This gives the
UI and audit logs a quick way to distinguish a narrow answer from broader multi-source
evidence.

Completed query payloads also include `neighbor_context`. These are non-cited segments
adjacent to returned citations, selected from the same document version with ordinal
distance `1` while staying inside `max_evidence_tokens`. They help the UI and operators
inspect surrounding context without turning nearby text into a citation. Each item stores
`source_segment_id`, title, anchor, ordinal, distance, text, and token count.

When `RETOS_AGENT_RUNTIME=deepagents`, the harness registers named
`evidence_checker` and `contradiction_checker` subagents. They receive the same
controlled corpus tools as the main agent, and the post-answer deterministic audits
still run before results are persisted.

`RETOS_AGENT_RUNTIME=deterministic` is the default for CI, Docker smoke, and local
development without downloaded model weights. It performs the controlled corpus search
and produces a deterministic grounded answer. `RETOS_AGENT_RUNTIME=deepagents` enables
`deepagents.create_deep_agent` synthesis with the same controlled corpus tools. For the
default local profile, pull the model first:

```bash
docker compose --profile models run --rm ollama-pull
RETOS_AGENT_RUNTIME=deepagents docker compose up --build
```

## LLM Providers

Provider discovery is viewer-safe and safe to call from the UI. It does not return API
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
  "agent_runtime": "deterministic",
  "paid_providers_enabled": false,
  "providers": [
    {
      "name": "local",
      "label": "Ollama local runtime",
      "default_model": "gemma4",
      "configured": true,
      "enabled": true,
      "paid": false,
      "reason": null,
      "missing_config": [],
      "base_url": "http://ollama:11434/"
    }
  ]
}
```

`fake` is reserved for tests. `openai`, `anthropic`, `google`, `openrouter`, and
`azure` require their provider-specific key/configuration and remain disabled unless
`RETOS_ALLOW_PAID_LLM=true`.

`missing_config` contains safe environment variable names, never secret values. For
example, an unconfigured OpenAI profile returns `["RETOS_OPENAI_API_KEY"]`; Azure can
return `RETOS_AZURE_OPENAI_API_KEY`, `RETOS_AZURE_OPENAI_ENDPOINT`, and
`RETOS_AZURE_OPENAI_DEPLOYMENT` depending on what is missing. If a paid profile is
selected as `RETOS_PROVIDER`, runtime security validation fails fast until both
`RETOS_ALLOW_PAID_LLM=true` and all required provider settings are present.

The Admin UI treats this catalog as safe operational metadata. It highlights the active
provider, active model, active agent runtime, and paid-provider policy, marks each
profile as active or available, shows configured versus missing-config state, preserves
the paid/local guardrail badges, and renders safe runtime hints such as the Ollama base
URL or missing environment variable names. It does not write provider settings or expose
secrets; runtime switching remains an explicit environment/configuration change that is
validated on startup.

Preview a safe local runtime switch plan:

```bash
curl --request POST http://localhost:8000/llm/runtime-plan \
  --header "Authorization: Bearer <token>" \
  --header "Content-Type: application/json" \
  --data '{"provider":"local","agent_runtime":"deepagents","allow_paid_llm":false}'
```

The response is a non-secret `.env` patch plus warnings and missing configuration names:

```json
{
  "provider": "local",
  "model": "ollama:gemma4",
  "agent_runtime": "deepagents",
  "paid_provider": false,
  "paid_providers_enabled": false,
  "can_start": true,
  "restart_required": true,
  "env": {
    "RETOS_PROVIDER": "local",
    "RETOS_AGENT_RUNTIME": "deepagents",
    "RETOS_MODEL": "ollama:gemma4",
    "RETOS_ALLOW_PAID_LLM": "false",
    "RETOS_OLLAMA_MODEL": "gemma4",
    "RETOS_OLLAMA_BASE_URL": "http://localhost:11434"
  },
  "missing_config": [],
  "warnings": ["Restart API and worker after changing runtime environment."],
  "reason": null
}
```

The planner never persists the switch, never returns API keys, and never performs a
provider call. Operators still apply the env changes through `.env`, Compose overrides,
or deployment configuration, then restart API and worker so startup validation can
enforce the selected profile.

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
- enough runnable request payload to repeat the eval from the run history when the
  original suite supports reruns

Run an opt-in SQuAD 2.0 eval from a mounted local dataset file:

```bash
curl --request POST http://localhost:8000/evals/squad \
  --header "Authorization: Bearer <token>" \
  --header "Content-Type: application/json" \
  --data '{
    "dataset_path":"dev-v2.0.json",
    "domain_id":"<optional_domain_id>",
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

Run an opt-in HotpotQA eval from a mounted local dataset file:

```bash
curl --request POST http://localhost:8000/evals/hotpotqa \
  --header "Authorization: Bearer <token>" \
  --header "Content-Type: application/json" \
  --data '{
    "dataset_path":"hotpot_dev_distractor_v1.json",
    "domain_id":"<optional_domain_id>",
    "max_cases":50,
    "write_report":true,
    "report_stem":"hotpotqa-dev-50"
  }'
```

The response shape matches `/evals/squad`; `report.suite_name` is `hotpotqa`, and
report exports are written under `RETOS_EVAL_REPORT_ROOT`.

Run the HotpotQA supporting-fact agent audit harness from the same mounted file:

```bash
curl --request POST http://localhost:8000/evals/hotpotqa-agent \
  --header "Authorization: Bearer <token>" \
  --header "Content-Type: application/json" \
  --data '{
    "dataset_path":"hotpot_dev_distractor_v1.json",
    "domain_id":"<optional_domain_id>",
    "max_cases":50,
    "write_report":true,
    "report_stem":"hotpotqa-agent-dev-50"
  }'
```

The response shape matches `/evals/hotpotqa`; `report.suite_name` is
`hotpotqa-agent`, and reruns reconstruct the durable dataset payload without calling
paid providers.

Run an opt-in OCR benchmark eval from a mounted local manifest, FUNSD directory, or
SROIE directory:

```bash
curl --request POST http://localhost:8000/evals/ocr-benchmark \
  --header "Authorization: Bearer <token>" \
  --header "Content-Type: application/json" \
  --data '{
    "dataset_path":"ocr-benchmark/manifest.json",
    "domain_id":"<optional_domain_id>",
    "dataset_format":"manifest",
    "max_cases":25,
    "write_report":true,
    "report_stem":"ocr-manifest-25",
    "max_character_error_rate":0.20,
    "max_word_error_rate":0.35,
    "max_pages":1
  }'
```

The response shape matches the other eval endpoints; `report.suite_name` is
`ocr-<dataset_format>`, `report.metrics` contains `character_error_rate` and
`word_error_rate`, plus `key_value_recall` when the dataset supplies expected fields.
When OCR benchmark cases include expected layout boxes, the same metrics object also
includes `reading_order_accuracy` and `layout_iou`.
Report exports are written under `RETOS_EVAL_REPORT_ROOT`.

Security and runtime notes:

- `dataset_path` must resolve inside `RETOS_EVAL_DATASET_ROOT`; traversal and
  absolute paths outside that root return `422`.
- `domain_id` is optional for dataset-backed evals. When present, the domain must exist
  and be accessible to the caller; RetOS stores it on the `eval.run` job, payload,
  journal events, progress events, and SSE payloads.
- Missing dataset files return `404` before any job is created.
- Adapter or schema errors return `422` and mark the created eval job failed.
- Reports are written under `RETOS_EVAL_REPORT_ROOT`; clients receive paths for
  later audit/export workflows.
- API smoke creates tiny SQuAD, HotpotQA, and Natural Questions fixtures and verifies
  those endpoints over HTTP. Docker smoke also creates an OCR benchmark manifest fixture
  and verifies `/evals/ocr-benchmark` through the running stack.

List recent persisted eval runs:

```bash
curl "http://localhost:8000/evals/runs?limit=6" \
  --header "Authorization: Bearer <token>"
```

Admins may list the full eval ledger or filter by `domain_id`. Viewers must provide a
granted `domain_id`, and only receive runs owned by that domain. The response is ordered
newest-first and includes runs that failed before a report was produced:

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

Use `domain_id=<domain_id>` to list only eval runs owned by a domain. Global built-in
eval runs have `job.domain_id=null` and are omitted from domain-filtered history.

Read trend summaries across persisted reported eval runs:

```bash
curl "http://localhost:8000/evals/runs/trends?limit=60" \
  --header "Authorization: Bearer <token>"
```

Admins may trend the full eval ledger or filter by `domain_id`. Viewers must provide a
granted `domain_id`, and trends are computed only from that domain's runs. The response
is grouped by `suite_name` and contains chronological points, latest run summary, pass
rate, and per-metric first/latest/min/max/average/delta values. Direction is
metric-aware: higher scores improve normal eval metrics, while lower values improve
`*_error_rate` OCR metrics. Use `suite_name=<name>` to narrow the trend to one suite.

Run the deterministic agent multi-hop eval suite:

```bash
curl --request POST http://localhost:8000/evals/agent-multihop \
  --header "Authorization: Bearer <token>"
```

The response shape matches `/evals/smoke`; `report.suite_name` is `agent-multihop`.
Metrics cover `query_plan`, `multi_hop_support`, `evidence_route`,
`citation_validity`, `grounded_answer`, and `budget_compliance`. The suite uses local
fixtures and the same bounded planned-search helper as `agent.query`, so it does not
call Ollama or paid providers.

Rerun a persisted eval run:

```bash
curl --request POST "http://localhost:8000/evals/runs/<job_id>/rerun" \
  --header "Authorization: Bearer <token>"
```

Admins may rerun any persisted runnable eval. Viewers may rerun dataset-backed evals
only when the original run has a `domain_id` they can access; global and built-in reruns
remain admin-only. The endpoint creates a new `eval.run` job using the original run's
persisted suite, dataset path, case limit, report settings, OCR thresholds, and OCR page
limit when present. The new job stores `rerun_from_job_id` in `job.payload` and includes
that origin in the new `eval.queued`/`eval.started` journal and progress payloads for
audit traceability. Dataset-backed reruns preserve the original `domain_id`. Runs with
missing dataset payloads or unknown suites return `422` instead of attempting a partial
rerun.

Compare two persisted eval runs:

```bash
curl "http://localhost:8000/evals/runs/compare?baseline_job_id=<old_job_id>&candidate_job_id=<new_job_id>" \
  --header "Authorization: Bearer <token>"
```

Admins may compare any same-scope eval runs. Viewers must provide a granted
`domain_id`, and both requested jobs must belong to that same domain. The endpoint reads
reports already stored in `job.payload.result`, does not call providers, and returns
per-metric deltas. Baseline and candidate runs must share the same `domain_id` scope;
comparing a global run with a domain-owned run returns `409`.

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

Gate a candidate run against a baseline before promoting a calibration:

```bash
curl "http://localhost:8000/evals/runs/regression-gate?baseline_job_id=<old_job_id>&candidate_job_id=<new_job_id>&metric_drop_tolerance=0.02&average_drop_tolerance=0.01" \
  --header "Authorization: Bearer <token>"
```

The regression gate uses the same access rules as comparison: admins may evaluate
same-scope runs globally, while viewers must pass a granted `domain_id` and can only
gate runs owned by that domain.

The gate reads persisted reports only. For normal metrics, negative deltas are
regressions. For `*_error_rate` metrics, positive deltas are regressions. The response
includes normalized deltas, per-metric regression flags, the average normalized delta,
and an overall `passed` boolean. Baseline and candidate runs must share the same
`domain_id` scope. The React console calls this endpoint from the
`Regression gate` action in the local eval history panel and renders the promote/block
decision beside the metric-level gate evidence.

### Frontend Runtime Notes

The React console reads `VITE_RETOS_API_URL` and falls back to `http://localhost:8000`.
The provider panel authenticates with `/auth/login`, stores the admin bearer token in
browser local storage under `retos.adminToken`, and then calls `/llm/providers` and
the workspace endpoints.

If a stored token receives `401 Unauthorized` while loading protected console data, the
console removes `retos.adminToken`, clears provider and workspace state, re-enables the
password field, and shows an explicit reconnect message. This keeps expired or revoked
sessions from staying sticky in local browser storage across provider, workspace, audit,
eval, query, job, and SSE actions.

Manual `fetch` paths such as upload, audit export, domain-grant deletion, and SSE
connection setup use the same response parser as JSON API calls. When the backend
returns a JSON `detail`, the console renders that operator-facing detail instead of a
generic status code.

Current console calls:

- `POST /auth/login`
- `GET /admin/users`
- `POST /admin/users`
- `PATCH /admin/users/{admin_user_id}/status`
- `PATCH /admin/users/{admin_user_id}/roles`
- `POST /admin/users/{admin_user_id}/password`
- `GET /llm/providers`
- `POST /llm/runtime-plan`
- `GET /domains`
- `POST /domains`
- `GET /domains/{domain_id}`
- `PATCH /domains/{domain_id}`
- `DELETE /domains/{domain_id}`
- `POST /domains/{domain_id}/restore`
- `GET /domains/{domain_id}/documents`
- `PATCH /documents/{document_id}`
- `DELETE /documents/{document_id}`
- `POST /documents/{document_id}/restore`
- `GET /documents/{document_id}/history`
- `GET /domains/{domain_id}/sources`
- `POST /domains/{domain_id}/sources`
- `PATCH /domains/{domain_id}/sources/{source_id}`
- `DELETE /domains/{domain_id}/sources/{source_id}`
- `POST /domains/{domain_id}/ingestions/text`
- `POST /domains/{domain_id}/ingestions/upload`
- `POST /sources/{source_id}/scan`
- `POST /domains/{domain_id}/index/rebuild`
- `POST /domains/{domain_id}/queries`
- `GET /evals/runs?limit=6[&domain_id=...]`
- `GET /evals/runs/trends?limit=60[&domain_id=...]`
- `GET /evals/runs/compare?baseline_job_id=...&candidate_job_id=...`
- `GET /evals/runs/regression-gate?baseline_job_id=...&candidate_job_id=...`
- `POST /evals/runs/{job_id}/rerun`
- `POST /evals/smoke`
- `POST /evals/agent-multihop`
- `POST /evals/squad`
- `POST /evals/hotpotqa`
- `POST /evals/hotpotqa-agent`
- `POST /evals/natural-questions`
- `POST /evals/ocr-benchmark`
- `GET /jobs?limit=12`
- `GET /jobs/{job_id}`
- `GET /documents/{document_id}/versions`
- `GET /document-versions/{version_id}/artifacts`
- `GET /document-versions/{version_id}/segments`
- `GET /audit/journal-events?limit=20`
- `GET /audit/progress-events?limit=20`

The UI treats the provider catalog as read-only operational status and admin users as
audited local accounts:

- `active.can_call=true` means the selected profile is ready to call.
- `paid=true` means the UI must show a cost warning before future query execution.
- `enabled=false` plus `reason` explains whether configuration or cost opt-in is missing.
- Runtime switch plans are previews only; they render non-secret env changes, missing
  config names, and restart warnings without mutating the running process.
- API keys are never returned to the browser.
- Admin passwords are write-only; the browser can create accounts with explicit roles,
  update persisted roles, toggle active state, and submit resets, but only receives
  account metadata, roles, and active/inactive state.

The workspace can create domains, select an active domain, archive and restore domains,
render document/source inventory for the active domain, inspect latest-version artifact
and segment evidence, create, edit, and remove sources, queue text and file upload ingestions, queue source
scans, rebuild the BM25 index, run local smoke/agent multi-hop/SQuAD/HotpotQA/HotpotQA
agent/Natural Questions/OCR benchmark evals, choose an eval domain scope for
dataset-backed runs, filtered history/trends, and viewer-safe domain reruns, read recent
jobs, inspect a selected job's full
payload/error/progress detail, read persisted audit/progress events, group progress by
job, filter the job ledger by status/kind, and send queries against the selected domain.
Query execution uses `run_inline=true` so the UI can render the answer, citations, query
plan, evidence route, multi-hop audit, neighbor context, provider metadata, budget usage,
evidence audit, and contradiction audit immediately.
Worker-backed query jobs are already available through the API by omitting `run_inline`;
the live progress panel reads the same SSE stream that ingestion, indexing, and agent
jobs write to.

Eval report responses include optional `metadata` with source and dataset provenance.
Dataset-backed runs record the adapter, resolved dataset path, `max_cases`, and API/CLI
source. The React console renders these values next to eval metrics, and the backend
copies them into the persisted job result plus eval journal/progress payloads for audit
reviews. In the `Local evals` panel, the `Eval scope` selector sends `domain_id` for
dataset-backed SQuAD, HotpotQA, HotpotQA agent, Natural Questions, and OCR benchmark
requests. Selecting a domain also adds `domain_id` to run-history, trend, comparison,
and regression-gate requests, so viewer sessions stay within their granted domain scope
and cross-run review actions operate on same-scope rows only. Leaving the selector on
`All evals` saves new dataset runs as global evals and reads unfiltered history, which
requires an admin token.

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
make audit-export-check EXPORT=retos-audit-export.json
```

Both endpoints require a bearer token and accept `limit` from `1` to `200`. Results are
ordered newest first. Admin tokens read the full local ledger; viewer tokens read only
events tied to granted domains through event payload `domain_id`, domain entity IDs, or
job-to-domain relationships.

The export endpoint follows the same admin/viewer visibility rules, accepts `limit` from
`1` to `1000`, returns `Content-Disposition: attachment;
filename="retos-audit-export.json"`, and sets `Cache-Control: no-store`. Export payloads
also include an offline integrity section. RetOS canonicalizes each event payload with
sorted JSON keys, hashes it with SHA-256, and persists `payload_hash`, `prev_hash`, and
`event_hash` on each journal/progress event at write time. The export recalculates the
payload hash from the payload being returned, compares that material against the
persisted event hash chain, reports continuity gaps caused by limited or scoped exports,
and returns a `failures` list with event ids, streams, reasons, expected values, and
actual values when integrity fails. This catches payload edits even when the stored hash
columns were not updated. It does not replace database backups, but it lets operators
detect accidental or malicious edits to persisted audit rows or exported audit packages.
Run `make audit-export-check EXPORT=retos-audit-export.json` against a downloaded export
to recompute payload hashes, event hashes, head hash, failure reasons, and continuity-gap
metadata offline.

Journal event shape:

```json
{
  "id": "<event_id>",
  "trace_id": "<job_id_or_trace_id>",
  "payload_hash": "<sha256>",
  "prev_hash": "<previous_event_hash_or_null>",
  "event_hash": "<sha256>",
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
  "trace_id": "<job_id_or_trace_id>",
  "payload_hash": "<sha256>",
  "prev_hash": "<previous_event_hash_or_null>",
  "event_hash": "<sha256>",
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
  "schema_version": "retos.audit-export.v2",
  "generated_at": "2026-06-27T00:00:00Z",
  "limit": 200,
  "journal_events": [],
  "progress_events": [],
  "integrity": {
    "algorithm": "sha256",
    "canonicalization": "json-sort-keys-v1",
    "valid": true,
    "event_count": 0,
    "head_hash": null,
    "failures": [],
    "continuity_gaps": [],
    "chain": [
      {
        "event_id": "<event_id>",
        "trace_id": "<job_id_or_trace_id>",
        "event_stream": "journal",
        "event_type": "job.created",
        "occurred_at": "2026-06-27T00:00:00Z",
        "payload_hash": "<sha256>",
        "prev_hash": null,
        "event_hash": "<sha256>"
      }
    ]
  }
}
```

The React audit panel uses these endpoints to show durable journal/progress evidence next
to the job ledger and to download a JSON audit export without putting bearer tokens in
URLs. After each export, the panel keeps a compact integrity summary visible with schema,
generation time, event count, head hash, algorithm, failure count, continuity-gap count,
and the `make audit-export-check` offline verifier command. SSE remains the live stream;
`/audit/*` is the reloadable persisted record.

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
in a compact ledger, deduplicates replayed events by stream id/event type, shows a live
summary for last event, observed jobs, status counts, and resume cursor, and reserves
space for empty, connected, and error states.

SSE ids are stable cursors:

- `progress:<progress_event_id>` is backed by the persisted `progress_events` table and
  can resume after API restarts.
- `live:<number>` is an in-memory notification cursor for process-local events.

On connect, the API replays recent persisted progress events before live memory events.
When `Last-Event-ID` is a `progress:*` cursor, the replay starts after that persisted
row. The React console tracks the latest `progress:*` id separately and sends it on the
next authenticated fetch reconnect.
Viewer tokens receive only persisted and live progress events tied to their granted
domains. Admin tokens receive the full local stream.

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

Retry a failed or cancelled runnable job:

```bash
curl --request POST --header "Authorization: Bearer <token>" \
  http://localhost:8000/jobs/<job_id>/retry
```

Worker-backed retries create a new `queued` job with the original kind, domain/source IDs,
and payload, add `retried_from_job_id` plus `retry_requested_at`, write
`job.retry_queued` journal/progress events, and dispatch the matching Celery task outside
`RETOS_ENV=test`. The generic retry endpoint supports worker-backed `ingest.source`,
`index.domain`, and `agent.query` jobs only when their payload contains enough data for
the worker to repeat the operation. It also supports failed or cancelled `eval.run` jobs
by delegating to the eval harness rerun path and preserving `rerun_from_job_id` in the
new eval job payload. It rejects active jobs, completed jobs, and manual jobs without a
runnable payload.

List jobs:

```bash
curl --header "Authorization: Bearer <token>" \
  "http://localhost:8000/jobs?limit=100"
```

Read one job:

```bash
curl --header "Authorization: Bearer <token>" http://localhost:8000/jobs/<job_id>
```

The React audit panel uses this endpoint for the per-job detail drilldown. It pairs the
returned job payload/error/timestamps with loaded `/audit/progress-events` rows that
share the same `job_id`, so operators can inspect a job without losing the append-only
audit trail.

## Persistence Notes

The API is wired through a SQLAlchemy async Unit of Work. Tests and smoke checks use SQLite with `RETOS_DATABASE_CREATE_ALL=true`. Production-like deployments should use Postgres and managed migrations. Login reads persisted `admin_users`; bootstrap settings only create the initial account idempotently.
