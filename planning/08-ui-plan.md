# UI Plan

## Goal

The UI is a working console, not a landing page. It must make background processing understandable: document scanning, OCR, indexing, agent tool calls, citations, and audit trails.

## Stack

- React + TypeScript.
- Vite.
- TanStack Query.
- TanStack Router.
- SSE/EventSource for live progress.
- Lucide icons.

## Navigation

| View | Purpose |
| --- | --- |
| Domains | Manage corpora and sources. |
| Documents | Uploads, mounts, scans, jobs, errors, previews. |
| Queries | Ask questions, select provider/budget, stream runs. |
| Evidence | Review citations, claims, segments, pages, artifacts. |
| Evals | Run and inspect local evals. |
| Settings/Admin | Admin account, providers, Ollama, budgets, audit export. |

## Implemented Frontend Contracts

- The admin provider panel logs in through `/auth/login` and reads `/llm/providers`.
- The provider catalog is rendered as operational status, not as editable secret
  management.
- Paid providers are visibly marked and remain blocked unless backend configuration and
  `RETOS_ALLOW_PAID_LLM=true` allow them.
- The workspace reads `/domains`, creates domains through `POST /domains`, keeps an
  active domain selector, and loads `/domains/{domain_id}/documents` for the selected
  corpus.
- The document inventory supports inline title updates through `PATCH
  /documents/{document_id}` and soft archive through `DELETE /documents/{document_id}`;
  both actions refresh durable audit/progress records and keep archived documents out of
  the active list.
- The workspace reads and creates sources through `/domains/{domain_id}/sources`, queues
  mounted source scans through `/sources/{source_id}/scan`, and queues BM25 rebuilds
  through `/domains/{domain_id}/index/rebuild`.
- The workspace queues uploaded `.txt`, `.md`, and `.pdf` files through
  `/domains/{domain_id}/ingestions/upload`, queues inline text corpora through
  `/domains/{domain_id}/ingestions/text`, refreshes documents, and reads recent jobs
  through `/jobs?limit=12`.
- The query workspace posts to `/domains/{domain_id}/queries` with `run_inline=true` and
  renders the grounded answer, job status, provider model, and citation cards without
  requiring users to paste domain UUIDs.
- The processing panel connects to `/events/progress` with authenticated `fetch`
  streaming, parses SSE frames, and renders a compact live progress ledger.
- The processing panel tracks the latest persisted `progress:*` SSE cursor and sends it
  as `Last-Event-ID` on reconnect, allowing reloadable progress replay after API
  restarts.
- The audit panel renders recent jobs with status/kind filtering, identifiers, timestamps,
  error state, and payload summaries.
- The audit panel reads `/audit/journal-events?limit=20` and
  `/audit/progress-events?limit=20` to render durable journal/progress records beside the
  live SSE stream.
- The audit panel downloads `/audit/export?limit=200` through an authenticated `fetch`
  call so the bearer token stays in headers and the exported JSON can be retained for
  review.
- The eval panel posts to `/evals/smoke`, reads `/evals/runs?limit=6`, and renders the
  returned `eval.run` job, metric scorecards, per-case pass/failure rows, and a compact
  newest-first run history.
- Browser smoke tests mock the API contract and verify provider, domain creation,
  document/source inventory, document edit/archive, file upload, text ingestion,
  scan/index queueing, job/audit filtering, persisted audit events, audit export, eval
  smoke execution, eval run history, query, and live progress flows.

## Processing UI

Show:

- Job timeline: scan, hash, extract, OCR, normalize, segment, index.
- Progress bars when totals are known.
- Counters for discovered, processed, skipped, and failed files.
- Last SSE event and timestamp.
- Retry action for failed jobs.
- Normalized error detail with suggested action.
- Snapshot recovery plus `Last-Event-ID` reconnect semantics. The live ledger and
  persisted resume cursor are implemented; richer per-job grouping remains pending.

## Accessibility

- Use semantic buttons, labels, and inputs.
- Use `aria-live="polite"` for important async updates.
- Give icon-only buttons accessible names.
- Keep focus states visible.
- Avoid layout shift during live updates.

## Browser Verification

Every UI slice should include a Playwright smoke test that:

- Opens the running React app.
- Verifies the primary view is visible.
- Checks meaningful controls by role/name.
- Checks live regions for async progress where applicable.
- Exercises reconnect/error states when SSE behavior changes.
