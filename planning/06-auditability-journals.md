# Auditability And Journals

## Goal

RetOS must be able to answer:

1. What happened.
2. Which evidence or data caused it.
3. How to verify or reproduce it.

## Current Journal Event Contract

The implemented durable event table and API expose:

| Field | Purpose |
| --- | --- |
| `id` | Event identifier. |
| `trace_id` | Nullable correlation key. Job-backed journal/progress events use the job id by default unless an explicit payload `trace_id` is provided. |
| `occurred_at` | UTC timestamp. |
| `actor` | Admin email, worker, or system actor string. |
| `event_type` | Stable event name. |
| `entity_type` | Domain, document, job, run, etc. |
| `entity_id` | Entity identifier. |
| `payload` | Minimal metadata without secrets. |

Current read endpoints:

- `GET /audit/journal-events?limit=20`
- `GET /audit/progress-events?limit=20`
- `GET /audit/export?limit=200`

Both require an authenticated bearer token. `admin` accounts can read the full local
ledger. `viewer` accounts can read only events tied to their granted domains through
event payload `domain_id`, domain entity IDs, or job-to-domain relationships. Audit-
producing mutations remain admin-only. Results return newest events first.

`/audit/export` returns `retos.audit-export.v2` snapshots with newest-first journal and
progress event lists plus an offline integrity section. The integrity block uses
SHA-256, sorted-key JSON canonicalization, per-event payload hashes, chronological
`trace_id`/`prev_hash`/`event_hash` links, a `head_hash`, and a `valid` flag computed
before the download is returned. The chain covers the exported slice only; durable
append-only hashes in the database remain a future hardening step.

## Future Hardening

The next audit hardening pass should add durable database-level `prev_hash` plus
`event_hash` columns for append-only ledger verification across exports and optional
OpenTelemetry propagation for external traces.

## Base Events

- `domain.created`
- `source.registered`
- `scan.started`
- `scan.completed`
- `document.discovered`
- `document_version.created`
- `artifact.created`
- `segment.created`
- `index_manifest.created`
- `agent_run.started`
- `tool_call.completed`
- `evidence.cited`
- `answer.finalized`
- `eval.queued`
- `eval.started`
- `eval.completed`
- `eval.failed`

## Evidence Ledger

Every document-grounded answer must include:

- Atomic claims.
- Supporting segment/page references.
- Source paths.
- Anchors.
- Confidence.
- Verification status.

Claims without evidence fail validation unless the response is explicitly an abstention or a non-document answer.
