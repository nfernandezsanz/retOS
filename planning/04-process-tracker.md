# Process Tracker

Last updated: 2026-06-27

Status values: `Not started`, `In progress`, `Blocked`, `In review`, `Complete`.

| Phase | Status | Implementation | Tests | Coverage | Auditability | Docs | Risks |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 - Open Source Bootstrap | In progress | Scaffold created | Backend, API smoke, frontend, browser smoke, Docker build, Docker stack smoke wired | 90.51% backend | Initial events only | In progress | Full product flows pending |
| 1 - Core Domain And Persistence | In progress | Admin/domain/source/document/artifact/segment persistence, audited admin account management, active-account token checks, soft document archive/restore, document field history, Alembic catalog schema, durable jobs lifecycle | Unit/API smoke/migration coverage | 90.51% backend | Admin create/status/password reset, document create/update/archive/restore/history, artifact/segment creation, and job transitions write journal/progress events | API and database guides added | Fine-grained non-admin roles still pending |
| 2 - Ingestion, OCR, And BM25 | In progress | Mounted `.txt`/`.md`/digital `.pdf` source scan, OCR fallback for image-only PDFs, text ingestion API, file upload ingestion API, Celery tasks, deterministic word chunking, extracted-text artifact persistence, Tantivy BM25 rebuild/search | Unit/API smoke/Docker worker smoke coverage started | 90.51% backend | Scan/upload/ingestion/indexing queue/start/success/failure write journal/progress/SSE events | API, Docker, database guides updated | OCR quality evals and page-level artifacts still pending |
| 3 - Deep Agents Runtime | In progress | LLM provider catalog, Deep Agents harness factory, and auditable `agent.query` jobs backed by indexed citations | Provider config, agent API, inline query, queued query, and harness tests started | 90.51% backend | Agent queue/start/success/failure write journal/progress/SSE events and persist result citations | API integration guide updated | Full Deep Agents model invocation and tool budgets still pending |
| 4 - Product UI | In progress | Operational console renders admin provider/account management, domain creation/selection, document/source inventory with inline title edit, archive visibility, archive, restore, and field history, file upload, text ingestion, scan/index queueing, live progress ledger, pipeline, query execution with citations, local eval smoke/SQuAD execution, exported report paths, eval history/comparison, job audit ledger, persisted journal/progress events, persisted SSE resume cursor, and audit export | Browser smoke covers provider login/catalog, admin user create/status/password reset, domain creation, document/source inventory, document edit/archive/restore/history, file upload, text ingestion, scan/index queueing, job/audit filtering, persisted audit events, persisted SSE replay cursor, audit export, eval smoke/SQuAD execution/history/comparison, live progress SSE parsing, and agent query result flow with mocked API | Frontend type/build gate active | Provider readiness, cost guardrails, admin account state, query/eval job status, selected domain, source/document evidence, filtered job payloads, persisted journal/progress rows, audit export snapshot, live progress events, SSE resume cursor, eval metrics/history/comparison, report paths, and citations visible in UI | API integration guide includes frontend runtime, admin users, upload, eval, eval comparison, document edit/archive/restore/history, SSE resume, and audit event/export notes | Document version diff views still pending |
| 5 - Evals | In progress | Deterministic local smoke suite for retrieval recall, citation validity, grounded answer terms, abstention, and citation budget compliance; SQuAD 2.0 opt-in adapter; JSON/Markdown report export; persisted cross-run comparison; admin API and React UI create durable `eval.run` jobs and list/compare persisted reports | Unit/API smoke/dataset adapter/export/comparison coverage plus `make eval-smoke`; CI runs eval smoke after backend tests; browser smoke covers SQuAD UI execution and comparison | 90.51% backend | Eval jobs persist reports, journal events, progress events, and SSE notifications; comparison reads persisted reports by job id; CLI/API can write filesystem reports; UI surfaces report paths; no paid provider calls | Eval guide and API integration guide updated with persisted run history, SQuAD usage, report export, comparison, UI execution, and public dataset roadmap | Additional adapters and OCR quality evals still pending |
| 6 - Alpha Release | Not started | Pending | Pending | Pending | Pending | Pending | Image size |

## Phase Checklist

```markdown
## Phase N - Name

- [ ] Scope confirmed
- [ ] ADRs added or updated
- [ ] Implementation complete
- [ ] Unit tests added
- [ ] Integration tests added where needed
- [ ] API smoke hits running endpoints
- [ ] Browser smoke opens the UI and verifies visible behavior
- [ ] Evals added or updated where needed
- [ ] Line coverage >= 90%
- [ ] Branch coverage >= 90%
- [ ] Tests avoid paid providers by default
- [ ] Journals/traces cover new events
- [ ] SSE progress is visible for long jobs/runs
- [ ] Docker/Compose updated where needed
- [ ] Docs updated
- [ ] Residual risks documented
```
