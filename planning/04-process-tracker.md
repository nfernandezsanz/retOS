# Process Tracker

Last updated: 2026-06-27

Status values: `Not started`, `In progress`, `Blocked`, `In review`, `Complete`.

| Phase | Status | Implementation | Tests | Coverage | Auditability | Docs | Risks |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 - Open Source Bootstrap | In progress | Scaffold created | Backend, API smoke, frontend, browser smoke, Docker build, Docker stack smoke wired | 90.90% backend | Initial events only | In progress | Full product flows pending |
| 1 - Core Domain And Persistence | In progress | Admin/domain/source/document/artifact/segment persistence, Alembic catalog schema, durable jobs lifecycle | Unit/API smoke/migration coverage | 90.90% backend | Document/artifact/segment/job creation and transitions write journal/progress events | API and database guides added | Role management UI still pending |
| 2 - Ingestion, OCR, And BM25 | In progress | Mounted `.txt`/`.md`/digital `.pdf` source scan, OCR fallback for image-only PDFs, text ingestion API, Celery tasks, deterministic word chunking, extracted-text artifact persistence, Tantivy BM25 rebuild/search | Unit/API smoke/Docker worker smoke coverage started | 90.90% backend | Scan/ingestion/indexing queue/start/success/failure write journal/progress/SSE events | API, Docker, database guides updated | OCR quality evals and page-level artifacts still pending |
| 3 - Deep Agents Runtime | In progress | LLM provider catalog, Deep Agents harness factory, and auditable `agent.query` jobs backed by indexed citations | Provider config, agent API, inline query, queued query, and harness tests started | 90.90% backend | Agent queue/start/success/failure write journal/progress/SSE events and persist result citations | API integration guide updated | Full Deep Agents model invocation and tool budgets still pending |
| 4 - Product UI | In progress | Operational console renders domain creation/selection, document/source inventory, text ingestion, scan/index queueing, live progress ledger, pipeline, query execution with citations, local eval smoke/SQuAD execution, exported report paths, eval history, job audit ledger, persisted journal/progress events, and admin provider catalog states | Browser smoke covers provider login/catalog, domain creation, document/source inventory, text ingestion, scan/index queueing, job/audit filtering, persisted audit events, eval smoke/SQuAD execution/history, live progress SSE parsing, and agent query result flow with mocked API | Frontend type/build gate active | Provider readiness, cost guardrails, query/eval job status, selected domain, source/document evidence, filtered job payloads, persisted journal/progress rows, live progress events, eval metrics/history, report paths, and citations visible in UI | API integration guide includes frontend runtime, eval, and audit event notes | File uploads, full document CRUD, audit export, and persisted SSE resume semantics still pending |
| 5 - Evals | In progress | Deterministic local smoke suite for retrieval recall, citation validity, grounded answer terms, abstention, and citation budget compliance; SQuAD 2.0 opt-in adapter; JSON/Markdown report export; admin API and React UI create durable `eval.run` jobs and list persisted reports | Unit/API smoke/dataset adapter/export coverage plus `make eval-smoke`; CI runs eval smoke after backend tests; browser smoke covers SQuAD UI execution | 90.90% backend | Eval jobs persist reports, journal events, progress events, and SSE notifications; CLI/API can write filesystem reports; UI surfaces report paths; no paid provider calls | Eval guide and API integration guide updated with persisted run history, SQuAD usage, report export, UI execution, and public dataset roadmap | Additional adapters and cross-run comparison still pending |
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
