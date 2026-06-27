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
| `occurred_at` | UTC timestamp. |
| `actor` | Admin email, worker, or system actor string. |
| `event_type` | Stable event name. |
| `entity_type` | Domain, document, job, run, etc. |
| `entity_id` | Entity identifier. |
| `payload` | Minimal metadata without secrets. |

Current read endpoints:

- `GET /audit/journal-events?limit=20`
- `GET /audit/progress-events?limit=20`

Both require an admin bearer token and return newest events first.

## Future Hardening

The next audit hardening pass should add:

- `trace_id` correlation with OpenTelemetry.
- Canonical payload hashes.
- `prev_hash` plus `event_hash` chain validation.
- Export endpoints for offline review.

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
