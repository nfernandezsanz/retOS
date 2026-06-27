# Process Tracker

Last updated: 2026-06-27

Status values: `Not started`, `In progress`, `Blocked`, `In review`, `Complete`.

| Phase | Status | Implementation | Tests | Coverage | Auditability | Docs | Risks |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 - Open Source Bootstrap | In progress | Scaffold created | Backend, API smoke, frontend, browser smoke, Docker build, Docker stack smoke wired | 90.41% backend | Initial events only | In progress | Full product flows pending |
| 1 - Core Domain And Persistence | In progress | Admin/domain/source/document/artifact/segment persistence, Alembic catalog schema, durable jobs lifecycle | Unit/API smoke/migration coverage | 90.41% backend | Document/artifact/segment/job creation and transitions write journal/progress events | API and database guides added | Role management UI still pending |
| 2 - Ingestion, OCR, And BM25 | In progress | Mounted `.txt`/`.md`/digital `.pdf` source scan, OCR fallback for image-only PDFs, text ingestion API, Celery tasks, deterministic word chunking, extracted-text artifact persistence, Tantivy BM25 rebuild/search | Unit/API smoke/Docker worker smoke coverage started | 90.41% backend | Scan/ingestion/indexing queue/start/success/failure write journal/progress/SSE events | API, Docker, database guides updated | OCR quality evals and page-level artifacts still pending |
| 3 - Deep Agents Runtime | Not started | Pending | Pending | Pending | Pending | Pending | Tool budgets |
| 4 - Product UI | Not started | Pending | Pending | Pending | Pending | Pending | Streaming UX |
| 5 - Evals | Not started | Pending | Pending | Pending | Pending | Pending | Stable scorers |
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
