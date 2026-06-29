# Auditor Evidence Matrix

This matrix maps the project objective to the evidence a human auditor should inspect.
It is intentionally local-first: GitHub Actions and release registry evidence are useful,
but the repository must still explain what can be proven from a checkout.

## Requirement Trace

| Objective Requirement | Current Evidence | Local Gate | Promotion Status |
| --- | --- | --- | --- |
| Friendly document and domain management UI | React console covers domain creation/selection, source inventory, document upload, text ingestion, edit/archive/restore/history, evidence inspection, and job progress. | `make frontend-e2e` | Local evidence ready; human visual review still required before production promotion. |
| Friendly query UI | React console surfaces provider readiness, selected domain, grounded answers, citations, query plan, evidence route, multi-hop audit, neighboring context, and budget usage. | `make frontend-e2e` | Local evidence ready; production pilot must validate target-user workflow. |
| Switchable local and paid LLM providers | Provider catalog exposes local Ollama `gemma4`, OpenAI, Anthropic, Google, OpenRouter, Azure, safe missing-configuration hints, and a non-secret runtime switch plan for provider/runtime env changes. Paid calls require explicit opt-in. | `make check`, `make api-smoke`, and `make frontend-e2e` | Local-safe by default; target deployment must review provider keys and cost policy before applying a switch plan. |
| Deep Agents runtime, not a classic LangGraph harness | Backend uses the Deep Agents harness profile with controlled corpus tools, bounded subqueries, named evidence/contradiction subagents, and deterministic fallback tests. | `make eval-agent-multihop` | Local deterministic evidence ready; live provider synthesis remains opt-in. |
| Auditable journals and traces | Journal/progress events persist trace IDs, canonical payload hashes, hash-chain links, export validation flags, and `/audit/export` review data. | `make api-smoke` and `make audit-manifest-check` | Local evidence ready; production promotion must review a fresh target-environment export. |
| SSE visibility for long processing | Jobs, ingestion, indexing, evals, and agent runs persist progress events and expose resumable SSE streams that the UI consumes. | `make api-smoke` and `make frontend-e2e` | Local evidence ready; target deployment should test proxy buffering and timeouts. |
| Docker-first reusable images | Compose builds one backend runtime image reused by API, worker, and migrate, plus one web image. Docker smoke validates runtime behavior and image ID parity. | `make docker-smoke` | Local evidence ready; release promotion still needs immutable GHCR digests. |
| Celery with RabbitMQ | Worker execution uses Celery and RabbitMQ; Docker smoke exercises worker-backed scan, upload ingestion, indexing, evals, and search. | `make docker-smoke` | Local evidence ready. |
| 90% or better test coverage | Backend total coverage is 95.25%; branch coverage is ratcheted at 90.54%. Tests and eval smoke avoid paid providers. | `make check` | Local evidence ready; coverage numbers must be refreshed when the suite changes. |
| Integration tests against real endpoints and UI | API smoke hits running HTTP endpoints; Playwright opens the React console; Docker smoke exercises the full Compose stack. | `make integration` and `make docker-smoke` | Local evidence ready; human promotion should rerun against the candidate environment. |
| Single local pre-audit acceptance gate | `make local-acceptance` runs backend quality, API/browser integration, frontend build, visual audit, Docker config, auditor handoff, and Docker stack smoke. | `make local-acceptance` | Local evidence ready; this gate is the preferred checkout-level command before human review. |
| Evals and calibration | Deterministic eval smoke, agent multi-hop evals, dataset-backed adapters, and 200-record/40-case calibration evidence are documented. | `make eval-smoke` and `make eval-agent-multihop` | Pilot-ready evidence; broader public calibration remains a promotion decision. |
| Branding, colors, and project image | RetOS ships a project card, favicon/mark, palette tokens, branding guide, visual audit screenshots, and README onboarding pills. | `make brand-check` and `make frontend-visual-audit` | Local evidence ready; human visual acceptance remains required. |
| Open source hygiene | MIT license, contribution guide, code of conduct, security policy, changelog, ADRs, planning, `.gitignore`, and `.dockerignore` are present and guarded. | `make auditor-static-check` | Local evidence ready. |
| Release and production handoff | Release workflow requests GHCR publish, SBOM/provenance, Cosign signing/verification, visual audit artifacts, and audit manifest artifacts. | `make release-check` and `make production-preflight` | Not production-promoted until tag publish, real digests, SBOM/provenance, Cosign evidence, and target-environment review are recorded. |

## Auditor Decision Rule

Treat a row as production-ready only when:

1. The listed local gate passes on the exact commit under review.
2. `make local-acceptance` passes on the same checkout when preparing a full local
   handoff.
3. Any row-specific human or target-environment review has been recorded.
4. The external promotion evidence in `docs/production-readiness.md` is complete.

The current repository state is suitable for a human production-readiness review, but
RetOS is not production-promoted yet and does not claim final production promotion until
the release evidence is captured.
