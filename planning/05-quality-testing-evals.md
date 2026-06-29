# Quality, Testing, And Evals

## Coverage Policy

- Minimum 90% total coverage.
- Target minimum 90% branch coverage.
- Current branch-only ratchet: 90.53%, enforced by CI after focused branch tests
  raised the ratchet above the 90% branch target without hiding gaps.
- Recommended 95% for auth, journals, identities, permissions, provider routing, and citation validation.

Default command:

```bash
make test
```

`make test` runs pytest with branch instrumentation, writes `backend/coverage.json`,
and then runs `backend/scripts/check_branch_coverage.py`. CI runs the same branch
ratchet after pytest so total coverage and branch coverage cannot drift silently; pass
`BRANCH_COVERAGE_MIN=90.53 make test` when auditing readiness against the current
branch coverage ratchet.

Reality-check commands:

```bash
make api-smoke
make eval-smoke
make eval-ocr
make eval-ocr-benchmark OCR_PATH=evals/datasets/ocr-benchmark/manifest.json
make eval-squad SQUAD_PATH=evals/datasets/dev-v2.0.json MAX_CASES=50 REPORT_DIR=evals/reports
make frontend-e2e
make integration
make docker-smoke
```

## Test Layers

| Layer | Scope | Paid Providers |
| --- | --- | --- |
| Unit | Domain, config, security, validators, budgets, adapters with fakes. | Never |
| Integration | Postgres, index rebuild, artifacts, API with fake providers. | Never by default |
| Contract | Tool schemas, provider interface, API responses, migrations. | Never by default |
| E2E | React UI, API, ingestion fixtures, query fixtures, SSE progress. | Never by default |
| Evals | Retrieval, grounding, citations, budget compliance, OCR quality. | Local/fake by default |
| Live smoke | OpenAI, Anthropic, Ollama real providers. | Explicit opt-in only |

## Cost Controls

```text
RETOS_ALLOW_PAID_LLM=false
RETOS_PROVIDER=fake
RETOS_LOCAL_MODEL=ollama:gemma4
```

Rules:

- Tests fail fast if a paid provider is used while paid calls are disabled.
- Provider SDKs are wrapped behind adapters.
- RabbitMQ is faked/eager for unit tests and only used in marked integration tests.
- SSE tests use synthetic events and reconnect semantics.
- API smoke tests must hit a running Uvicorn server over HTTP.
- Browser smoke tests must open the actual React app with Playwright.

## Continuous Reality Checks

The project should never rely only on isolated unit tests. Every implementation slice should add or update:

| Check | Trigger |
| --- | --- |
| API smoke | Any route, auth, SSE, provider, or job behavior changes. |
| Browser smoke | Any user-visible UI, route, status, timeline, or evidence behavior changes. |
| Compose config | Docker, env, worker, service, or port changes. |
| Docker build/dry-run | Dockerfile, dependency, or image-role changes. |
| Docker stack smoke | Compose services, healthchecks, ports, volumes, Dockerfile runtime, or entrypoints change. |
| Evals smoke | Retrieval, agent, citation, or answer behavior changes. |

## Initial Eval Types

| Eval | Measures | Default Scorer |
| --- | --- | --- |
| Retrieval recall | Expected segments appear in candidates. | Deterministic |
| Citation validity | Citations point to stable segments/pages. | Deterministic |
| Grounded claims | Claims have supporting evidence. | Rule + fixture |
| Abstention | Missing evidence leads to no-answer behavior. | Deterministic |
| Budget compliance | Runs respect tool and runtime budgets. | Deterministic |
| OCR character error rate | OCR output preserves normalized characters. | Deterministic local OCR or mocked adapter |
| OCR word error rate | OCR output preserves searchable word tokens. | Deterministic local OCR or mocked adapter |
| Provider parity | Provider switching preserves contracts. | Fake providers |

## Implemented Eval Smoke

`make eval-smoke` runs `backend/scripts/run_eval_smoke.py` with a temporary Tantivy
index. It does not call providers, does not download datasets, and does not require
RabbitMQ or Postgres.

Current metrics:

- Retrieval recall.
- Citation validity.
- Grounded answer terms.
- Abstention when evidence is missing.
- Citation budget compliance.

The smoke suite is included in `make check` and GitHub Actions. API smoke also
creates tiny SQuAD 2.0 and HotpotQA fixtures, posts them to `/evals/squad`,
`/evals/hotpotqa`, and `/evals/hotpotqa-agent`, verifies the durable `eval.run`
responses, checks that JSON/Markdown reports were written, and compares the smoke run
against the SQuAD run over HTTP. Docker smoke additionally runs the OCR
benchmark endpoint against a generated manifest fixture and checks report export in the
shared eval report volume. Browser smoke exercises the React SQuAD, HotpotQA,
HotpotQA-agent, Natural Questions, and OCR benchmark controls with mocked API responses
and verifies visible suite history, report paths, and cross-run comparison.

`make eval-fetch-dataset PROFILE=...` is the only supported networked dataset helper.
It downloads bounded public samples into `evals/datasets/` for local research, refuses
overwrites by default, records the effective `source_url`, supports retryable primary
and mirror URLs, and remains outside CI. Tests cover its samplers, overwrite guards,
local gzip sampling, and mirror fallback with mocked/local payloads so quality gates do
not depend on public endpoints.
The `nq-open-train-adapter` profile converts NQ-Open samples into the RetOS Natural
Questions adapter shape with synthetic local evidence documents so real user-question
samples can run through `make eval-natural-questions` without requiring the full
annotated Natural Questions corpus. The `nq-simplified-local` profile samples an
operator-provided official simplified Natural Questions `.jsonl` or `.jsonl.gz` file into
a bounded local JSONL slice, giving the project a real full document-shape eval path
without adding network or large-file requirements to CI.

`make eval-calibration` orchestrates bounded public calibration across SQuAD, HotpotQA,
HotpotQA-agent, and the NQ-Open adapter. It fetches or reuses samples, runs each suite,
writes per-suite JSON/Markdown reports, and emits
`evals/reports/calibration/manifest.json` with provenance, metrics, report paths,
optional metric-gate decisions, and dataset reuse state. Release candidates can pass
global gates such as `METRIC_GATES="retrieval_recall=0.80 citation_validity=1.0"` or
target-scoped gates such as
`METRIC_GATES="squad.retrieval_recall=0.80 hotpotqa-agent.multi_hop_support=0.70"` to
fail the manifest when selected real-dataset metrics fall below promotion thresholds.
`make eval-calibration-evidence` exports the ignored manifest into path-safe Markdown
release evidence under `docs/releases/evidence/`; fetched samples also get ignored
metadata sidecars so reused runs keep source URL, record count, source path, and license
provenance. Calibration remains opt-in because it can perform network downloads, while
unit coverage mocks fetch and eval execution so CI stays deterministic and free.

`make eval-calibration-compare BASELINE=<manifest> CANDIDATE=<manifest>` compares two
calibration manifests for release trend evidence. The comparison requires the candidate
to pass its own gates, keep every baseline target and numeric metric, retain at least the
baseline record/case counts, and avoid metric regression beyond `MAX_REGRESSION`. The
Markdown export omits local dataset/report paths and keeps only source URLs, license
notes, metric deltas, and record/case deltas. This is used to prove bounded sample growth
without relying on ignored local report files.

## Implemented OCR Quality Smoke

`make eval-ocr` runs `backend/scripts/run_eval_smoke.py --suite ocr-smoke`. It
generates tiny image-only PDFs, sends them through the ingestion OCR function, and
reports character error rate plus word error rate as JSON or Markdown. Unit tests mock
OCR so CI stays deterministic; the local command is opt-in because real Tesseract
availability varies by machine and container profile.

OCR fallback ingestion now also persists `ocr_page_text` artifacts with stable
`#page=N` URI anchors.

## Implemented OCR Benchmark Adapters

`make eval-ocr-benchmark` runs `backend/scripts/run_eval_smoke.py --suite ocr-benchmark`.
The adapter supports local manifest files, FUNSD directories, and SROIE directories.
All paths are opt-in, bounded by `MAX_CASES`, and resolved under the dataset root so CI
does not download public data or call paid providers.

## Public Dataset Candidates

| Dataset | Fit |
| --- | --- |
| SQuAD 2.0 | Implemented as an opt-in local adapter and admin API run for paragraph QA plus unanswerable/abstention cases, with optional JSON/Markdown report export. |
| HotpotQA | Implemented as an opt-in local adapter and admin API run for multi-hop retrieval and supporting-fact evaluation, with optional JSON/Markdown report export. `hotpotqa-agent` converts eligible supporting-fact cases into deterministic agent audit cases for query-plan, evidence-route, bridge-term, grounding, citation, and budget calibration through CLI, admin API, rerun, and React controls. |
| Natural Questions | Implemented as an opt-in local adapter and admin API run for real user questions with Wikipedia evidence; NQ-Open samples can also be converted into adapter-compatible synthetic evidence for early query-shape calibration, and official simplified NQ `.jsonl(.gz)` files can be sampled locally for full document-shape retrieval pressure. |
| FUNSD | Implemented as an opt-in OCR benchmark adapter for form image/text pressure; derives deterministic key-value recall and layout boxes from question/answer links and annotation boxes when present. |
| ICDAR 2019 SROIE | Implemented as an opt-in OCR benchmark adapter for receipt OCR pressure; reads optional entity files for deterministic key-value recall and box files for reading-order/Layout IoU scoring. |
| ISRI OCR Evaluation Tools | OCR scoring methodology reference for CER/WER-style checks. |

Dataset adapters must be opt-in and must not make CI depend on network downloads.
