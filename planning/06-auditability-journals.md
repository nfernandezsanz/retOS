# Auditability And Journals

## Goal

RetOS must be able to answer:

1. What happened.
2. Which evidence or data caused it.
3. How to verify or reproduce it.

## Journal Event

| Field | Purpose |
| --- | --- |
| `id` | Ordered event identifier. |
| `created_at` | UTC timestamp. |
| `trace_id` | Correlation with OpenTelemetry. |
| `actor_type` | `user`, `system`, `agent`, or `worker`. |
| `event_type` | Stable event name. |
| `subject_type` | Domain, document, job, run, etc. |
| `subject_id` | Subject identifier. |
| `payload_json` | Minimal metadata without secrets. |
| `payload_hash` | Canonical payload hash. |
| `prev_hash` | Previous event hash. |
| `event_hash` | Current event hash. |

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
- `eval_run.completed`

## Evidence Ledger

Every document-grounded answer must include:

- Atomic claims.
- Supporting segment/page references.
- Source paths.
- Anchors.
- Confidence.
- Verification status.

Claims without evidence fail validation unless the response is explicitly an abstention or a non-document answer.
