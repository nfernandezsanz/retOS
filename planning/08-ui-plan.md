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
| Overview | Short operating snapshot with posture, metrics, and workflow entry cards. |
| Documents | Manage domains, sources, uploads, mounted scans, indexing, archive/history, and document evidence. |
| Queries | Ask grounded questions, inspect citations, budgets, query plans, evidence routes, and live SSE progress. |
| Evals | Run and inspect local evals, report paths, history, trends, comparisons, reruns, and regression gates. |
| Audit | Review jobs, retries, journal events, persisted progress, per-job detail, and exportable evidence. |
| Admin | Load provider readiness and manage admin/viewer accounts plus per-domain grants. |

The console uses hash-addressable sections (`#overview`, `#documents`, `#queries`,
`#evals`, `#audit`, and `#admin`) rather than one long page. The sidebar and
workspace section switcher keep the same destinations, expose `aria-current`, and use
hover/focus tooltips on navigation and primary actions so operators can understand each
workflow without extra instructional copy. Only the active section renders visibly; this
keeps local browser sessions short, scan-friendly, and easy to validate with Playwright.

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
  /documents/{document_id}`, soft archive through `DELETE /documents/{document_id}`, an
  archived visibility toggle, restore through `POST /documents/{document_id}/restore`,
  and field history through `GET /documents/{document_id}/history`; these actions refresh
  durable audit/progress records and keep active/archived state explicit.
- Each document row can inspect latest-version evidence through
  `/documents/{document_id}/versions`, `/document-versions/{version_id}/artifacts`, and
  `/document-versions/{version_id}/segments`, surfacing derived artifact URIs and
  searchable segment anchors without leaving the inventory.
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
  error state, payload summaries, and an inspectable detail panel backed by
  `/jobs/{job_id}`.
- The audit panel reads `/audit/journal-events?limit=20` and
  `/audit/progress-events?limit=20` to render durable journal/progress records beside the
  live SSE stream.
- The audit panel downloads `/audit/export?limit=200` through an authenticated `fetch`
  call so the bearer token stays in headers and the exported JSON can be retained for
  review.
- The admin panel reads `/admin/users`, creates `admin` or `viewer` accounts, renders
  account roles, updates active state, submits password resets, and manages per-domain
  viewer grants without rendering hashes or secrets.
- The eval panel posts to `/evals/smoke`, `/evals/agent-multihop`, `/evals/squad`,
  `/evals/hotpotqa`, `/evals/hotpotqa-agent`, `/evals/natural-questions`, and
  `/evals/ocr-benchmark`, reads `/evals/runs?limit=6`,
  compares reported runs through `/evals/runs/compare`, and renders the returned
  `eval.run` jobs, metric scorecards, per-case pass/failure rows, report paths,
  newest-first run history, and per-metric deltas.
- The audit panel groups persisted progress by `job_id` before showing the raw
  journal/progress ledgers, so operators can scan each job's event count, latest
  state, and final progress message without losing the underlying audit trail.
- The selected job detail panel shows status, kind, domain/source IDs, timestamps,
  full JSON payload, error text, and persisted progress events for the selected job.
- Failed and cancelled runnable jobs expose a retry action. The UI posts to
  `/jobs/{job_id}/retry`, selects the new queued job, and shows its retry metadata in the
  detail panel.
- The shell includes a keyboard-visible skip link to the workspace, keeps sidebar focus
  rings visible, and verifies mobile provider/eval/audit surfaces do not create
  document-level horizontal overflow.
- The shell renders a compact Overview first, then separates Documents, Queries, Evals,
  Audit, and Admin into focused hash-addressable sections with matching sidebar and
  workspace controls. Hover/focus tooltips describe navigation targets and high-impact
  actions without adding permanent explanatory text.
- Browser smoke tests mock the API contract and verify provider, admin user roles,
  per-domain viewer grants, domain
  creation, document/source inventory, document evidence inspection,
  document edit/archive/restore/history, file
  upload, text ingestion, scan/index queueing, job/audit filtering, persisted audit
  events, audit export, eval smoke execution, eval run history, query, and live
  progress flows.

## Processing UI

Show:

- Job timeline: scan, hash, extract, OCR, normalize, segment, index.
- Progress bars when totals are known.
- Counters for discovered, processed, skipped, and failed files.
- Last SSE event and timestamp.
- Retry action for failed jobs. Implemented for worker-backed jobs and persisted eval
  runs through the audit panel; eval reruns also remain explicit through the eval
  controls.
- Normalized error detail with suggested action.
- Snapshot recovery plus `Last-Event-ID` reconnect semantics. The live ledger,
  persisted resume cursor, per-job progress grouping, and per-job detail drilldowns
  are implemented.

## Accessibility

- Use semantic buttons, labels, and inputs.
- Keep the primary workspace as the document `main` region and expose a skip link before
  the sidebar navigation.
- Use `aria-live="polite"` for important async updates.
- Give icon-only buttons accessible names.
- Keep focus states visible.
- Avoid layout shift during live updates.

## Browser Verification

Every UI slice should include a Playwright smoke test that:

- Opens the running React app.
- Verifies the primary view is visible.
- Checks meaningful controls by role/name.
- Checks keyboard focus paths, including the skip link, when navigation changes.
- Checks mobile horizontal overflow on dense operational panels.
- Checks live regions for async progress where applicable.
- Exercises reconnect/error states when SSE behavior changes.
