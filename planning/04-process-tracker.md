# Process Tracker

Last updated: 2026-06-27

Status values: `Not started`, `In progress`, `Blocked`, `In review`, `Complete`.

| Phase | Status | Implementation | Tests | Coverage | Auditability | Docs | Risks |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 - Open Source Bootstrap | In progress | Scaffold created | Backend, API smoke, frontend, browser smoke wired | 94.87% backend | Initial events only | In progress | Full Docker build awaits daemon smoke |
| 1 - Core Domain And Persistence | Not started | Pending | Pending | Pending | Pending | Pending | Schema design |
| 2 - Ingestion, OCR, And BM25 | Not started | Pending | Pending | Pending | Pending | Pending | OCR quality |
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
