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

## Test Layers

| Layer | Scope | Paid Providers |
| --- | --- | --- |
| Unit | Domain, config, security, validators, budgets, adapters with fakes. | Never |
| Integration | Postgres, index rebuild, artifacts, API with fake providers. | Never by default |
| Contract | Tool schemas, provider interface, API responses, migrations. | Never by default |
| E2E | React UI, API, ingestion fixtures, query fixtures, SSE progress. | Never by default |
| Evals | Retrieval, grounding, citations, budget compliance. | Local/fake by default |
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

## Initial Eval Types

| Eval | Measures | Default Scorer |
| --- | --- | --- |
| Retrieval recall | Expected segments appear in candidates. | Deterministic |
| Citation validity | Citations point to stable segments/pages. | Deterministic |
| Grounded claims | Claims have supporting evidence. | Rule + fixture |
| Abstention | Missing evidence leads to no-answer behavior. | Deterministic |
| Budget compliance | Runs respect tool and runtime budgets. | Deterministic |
| Provider parity | Provider switching preserves contracts. | Fake providers |
