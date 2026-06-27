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

## Processing UI

Show:

- Job timeline: scan, hash, extract, OCR, normalize, segment, index.
- Progress bars when totals are known.
- Counters for discovered, processed, skipped, and failed files.
- Last SSE event and timestamp.
- Retry action for failed jobs.
- Normalized error detail with suggested action.
- Snapshot recovery plus `Last-Event-ID` reconnect semantics.

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
