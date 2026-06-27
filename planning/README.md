# Planning

Last updated: 2026-06-27

This directory is the living implementation guide for RetOS: a Dockerized, open source, local-first research system for auditable document work.

## Documents

| Document | Purpose |
| --- | --- |
| [00-research-notes.md](00-research-notes.md) | Verified research notes and implementation consequences. |
| [01-product-scope.md](01-product-scope.md) | Product goals, non-goals, users, and MVP scope. |
| [02-architecture.md](02-architecture.md) | Architecture, data model, boundaries, and patterns. |
| [03-roadmap-phases.md](03-roadmap-phases.md) | Implementation phases with exit criteria. |
| [04-process-tracker.md](04-process-tracker.md) | Phase tracker and checklist. |
| [05-quality-testing-evals.md](05-quality-testing-evals.md) | Coverage, mocks, tests, evals, and CI policy. |
| [06-auditability-journals.md](06-auditability-journals.md) | Journals, ledgers, traces, retention, and review. |
| [07-agent-provider-strategy.md](07-agent-provider-strategy.md) | Deep Agents and provider strategy. |
| [08-ui-plan.md](08-ui-plan.md) | React UI plan for documents, jobs, queries, and evidence. |
| [09-open-source-docker.md](09-open-source-docker.md) | Docker, release, and open source packaging. |
| [10-implementation-decisions.md](10-implementation-decisions.md) | Decisions locked for implementation. |

## Working Rules

1. Open each phase in the tracker before implementation starts.
2. No phase is done without tests, coverage, auditability, and docs.
3. Tests must not call paid providers by default.
4. The primary agent runtime is `deepagents.create_deep_agent`.
5. The React console is the product UI; Django admin and server-rendered templates are not part of the MVP.
