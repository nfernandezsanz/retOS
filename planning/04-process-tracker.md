# Process Tracker

Last updated: 2026-06-28

Status values: `Not started`, `In progress`, `Blocked`, `In review`, `Complete`.

| Phase | Status | Implementation | Tests | Coverage | Auditability | Docs | Risks |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 - Open Source Bootstrap | In progress | Scaffold created | Backend, API smoke, frontend, browser smoke, Docker build, Docker stack smoke wired | 90.31% backend | Initial events only | In progress | Full product flows pending |
| 1 - Core Domain And Persistence | In progress | Admin/domain/source/document/artifact/segment persistence, audited admin account management with persisted `admin`/`viewer` roles, active-account and persisted-role token checks, viewer-safe read-only authorization matrix, per-domain viewer grants for domain-scoped resources, audit filtering, SSE replay filtering, admin-only eval history/comparison, soft document archive/restore, document field history, Alembic catalog schema, durable jobs lifecycle | Unit/API smoke/migration/authorization/audit/eval visibility coverage | 90.31% backend | Admin create/status/role/password reset/domain grant changes, document create/update/archive/restore/history, artifact/segment creation, eval run reads, and job transitions write journal/progress events; viewers can read granted domain state and audit trails without mutating state | API, database, and auditability guides added | Dataset-backed eval scoping remains admin-only until eval jobs become domain-owned |
| 2 - Ingestion, OCR, And BM25 | In progress | Mounted `.txt`/`.md`/digital `.pdf` source scan, OCR fallback for image-only PDFs, text ingestion API, file upload ingestion API, Celery tasks, deterministic word chunking, extracted-text artifact persistence, page-level OCR text artifacts, Tantivy BM25 rebuild/search, opt-in OCR quality smoke over generated image-only PDFs, OCR benchmark adapters for manifest/FUNSD/SROIE datasets, and deterministic key-value recall scoring | Unit/API smoke/Docker worker smoke/OCR eval coverage started | 90.31% backend | Scan/upload/ingestion/indexing/OCR artifact queue/start/success/failure write journal/progress/SSE events | API, Docker, database, and eval guides updated | Geometric layout-aware OCR scoring still pending |
| 3 - Deep Agents Runtime | In progress | LLM provider catalog, Deep Agents harness factory with restricted RetOS profile, controlled corpus tools, source mapping, table/key-value inspection, opt-in Deep Agents synthesis, named evidence/contradiction subagents, post-answer evidence audit, deterministic contradiction audit, and auditable `agent.query` jobs backed by indexed citations with persisted search/citation/evidence/runtime budget usage | Provider config, corpus tools, source/table tools, agent API, inline query, queued query, budget enforcement, mocked Deep Agents invocation, evidence audit, contradiction audit, named subagents, and harness tests started | 90.31% backend | Agent queue/start/success/failure write journal/progress/SSE events and persist result citations, evidence audit, contradiction audit, runtime, and budget usage | API integration guide and agent strategy updated | Richer multi-hop review and neighboring context expansion still pending |
| 4 - Product UI | In progress | Operational console renders admin provider/account management, domain creation/selection, document/source inventory with inline title edit, archive visibility, archive, restore, and field history diffs, file upload, text ingestion, scan/index queueing, live progress ledger, pipeline, query execution with citations and budget usage, local eval smoke/SQuAD/HotpotQA/Natural Questions/OCR benchmark execution, exported report paths, eval history/comparison/rerun actions, job audit ledger, per-job progress grouping, per-job detail drilldown, failed/cancelled job retry, persisted journal/progress events, persisted SSE resume cursor, and audit export | Browser smoke covers provider login/catalog, admin user create/status/password reset, domain creation, document/source inventory, document edit/archive/restore/history, file upload, text ingestion, scan/index queueing, job/audit filtering, persisted audit events, per-job progress grouping, per-job detail inspection, failed-job retry, persisted SSE replay cursor, audit export, eval smoke/SQuAD/HotpotQA/Natural Questions/OCR benchmark execution/history/comparison/rerun, live progress SSE parsing, and agent query result/budget flow with mocked API | Frontend type/build gate active | Provider readiness, cost guardrails, admin account state, query/eval job status, selected domain, source/document evidence, filtered job payloads, selected job payload/error/progress/retry details, per-job progress summaries, persisted journal/progress rows, audit export snapshot, live progress events, SSE resume cursor, eval metrics/history/comparison/rerun state, report paths, citations, and query budget usage visible in UI | API integration guide includes frontend runtime, admin users, upload, eval, eval comparison/rerun, document edit/archive/restore/history, job detail inspection, job retry, SSE resume, agent budgets, and audit event/export notes | Job retry is limited to worker-backed jobs; eval reruns depend on persisted runnable payloads |
| 5 - Evals | In progress | Deterministic local smoke suite for retrieval recall, citation validity, grounded answer terms, abstention, and citation budget compliance; SQuAD 2.0 opt-in adapter; HotpotQA opt-in multi-hop adapter; Natural Questions opt-in real-query adapter; opt-in OCR quality smoke with CER/WER/key-value recall; OCR benchmark adapters for manifest/FUNSD/SROIE; JSON/Markdown report export; persisted cross-run comparison; persisted rerun endpoint; admin API and React UI create durable `eval.run` jobs and list/compare/rerun persisted reports | Unit/API smoke/dataset adapter/OCR scorer/export/comparison/rerun coverage plus `make eval-smoke`; API smoke hits eval rerun over HTTP; CI runs eval smoke after backend tests; browser smoke covers SQuAD/HotpotQA/Natural Questions/OCR benchmark UI execution, rerun, and comparison; Docker smoke runs OCR benchmark over HTTP | 90.31% backend | Eval jobs persist reports, rerun origin, journal events, progress events, and SSE notifications; comparison reads persisted reports by job id; rerun reconstructs from persisted payloads; CLI/API can write filesystem reports; UI surfaces report paths; no paid provider calls | Eval guide and API integration guide updated with persisted run history, SQuAD/HotpotQA/Natural Questions/OCR benchmark usage, OCR quality smoke, key-value recall, report export, comparison, rerun, UI execution, and public dataset roadmap | Geometric layout-aware OCR evals still pending |
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
