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
| `payload_hash` | SHA-256 hash of the canonical event payload. |
| `prev_hash` | Previous journal/progress event hash in the persisted append-only chain. |
| `event_hash` | SHA-256 hash of event identity, stream, type, timestamp, payload hash, trace id, and previous hash. |
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
SHA-256, sorted-key JSON canonicalization, per-event payload hashes recomputed from the
returned payloads, chronological `trace_id`/`prev_hash`/`event_hash` links, a `head_hash`,
continuity checks inside the exported slice, a `failures` list for mismatched entries,
and a `valid` flag computed before the download is returned. New writes persist the same
hash-chain fields in the database, and migration `0008_audit_hash_chain_columns` backfills
existing rows. Because exports can be limited slices, `valid=true` means each included
event's current payload still matches its persisted hash-chain material and each
non-first event links to the previous included event; a first `prev_hash` may legitimately
point to an event outside the exported slice.

## Future Hardening

The next audit hardening pass should add optional OpenTelemetry propagation for external
traces and operator tooling for full-ledger verification reports.

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

Eval reruns must keep `rerun_from_job_id` in the new job payload and in the new
`eval.queued`/`eval.started` journal and progress payloads so repeated runs can be
traced back to the source report without depending on UI state.

## Evidence Ledger

Every document-grounded answer must include:

- Atomic claims.
- Supporting segment/page references.
- Source paths.
- Anchors.
- Confidence.
- Verification status.

Claims without evidence fail validation unless the response is explicitly an abstention or a non-document answer.
