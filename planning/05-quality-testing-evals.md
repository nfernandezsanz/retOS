# Quality, Testing, And Evals

## Coverage Policy

- Minimum 90% line coverage.
- Minimum 90% branch coverage.
- Recommended 95% for auth, journals, identities, permissions, provider routing, and citation validation.

Default command:

```bash
cd backend
pytest
```

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
creates a tiny SQuAD 2.0 fixture, posts it to `/evals/squad`, verifies the durable
`eval.run` response, checks that JSON/Markdown reports were written, and compares the
smoke run against the SQuAD run over HTTP. Docker smoke additionally runs the OCR
benchmark endpoint against a generated manifest fixture and checks report export in the
shared eval report volume. Browser smoke exercises the React SQuAD, HotpotQA, Natural
Questions, and OCR benchmark controls with mocked API responses and verifies visible
suite history, report paths, and cross-run comparison.

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
| HotpotQA | Implemented as an opt-in local adapter and admin API run for multi-hop retrieval and supporting-fact evaluation, with optional JSON/Markdown report export. |
| Natural Questions | Implemented as an opt-in local adapter and admin API run for real user questions with Wikipedia evidence. |
| FUNSD | Implemented as an opt-in OCR benchmark adapter for form image/text pressure; layout-aware scoring remains future work. |
| ICDAR 2019 SROIE | Implemented as an opt-in OCR benchmark adapter for receipt OCR pressure; key-value extraction scoring remains future work. |
| ISRI OCR Evaluation Tools | OCR scoring methodology reference for CER/WER-style checks. |

Dataset adapters must be opt-in and must not make CI depend on network downloads.
