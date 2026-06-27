# Research Notes

Last verified: 2026-06-27

## Deep Agents

Sources:

| Topic | Source |
| --- | --- |
| Deep Agents overview | https://docs.langchain.com/oss/python/deepagents/overview |
| Customization and backends | https://docs.langchain.com/oss/python/deepagents/customization |
| Skills and backends | https://docs.langchain.com/oss/python/deepagents/skills |
| Streaming | https://docs.langchain.com/oss/python/deepagents/streaming |

Findings:

- `deepagents` is an agent harness with planning, subagents, virtual filesystem, permissions, memory, skills, streaming, and human-in-the-loop support.
- LangGraph is used internally, but RetOS should enter through `create_deep_agent`, not a custom classic `StateGraph`.
- The harness filesystem does not replace the RetOS virtual corpus filesystem. The real corpus is exposed only through controlled tools.

Decisions:

- Use `deepagents.create_deep_agent` for the research runtime.
- Do not build the primary agent loop with classic LangGraph in the MVP.
- Use subagents for evidence checking, contradiction checks, source mapping, and table inspection.

## Ollama And Gemma 4

Sources:

| Topic | Source |
| --- | --- |
| Gemma 4 in Ollama | https://ollama.com/library/gemma4 |
| Gemma 4 tags | https://ollama.com/library/gemma4/tags |

Findings:

- `gemma4` is available in Ollama.
- The local profile can run through the Ollama HTTP API.
- Exact tags can be pinned later for reproducible evals.

Decisions:

- Default local profile: `ollama:gemma4`.
- Do not bake model weights into the application image.
- Compose includes Ollama and a persistent model volume.

## Backend, UI, Jobs, And Search

Sources:

| Topic | Source |
| --- | --- |
| Django async | https://docs.djangoproject.com/en/5.2/topics/async/ |
| Django admin | https://docs.djangoproject.com/en/5.2/ref/contrib/admin/ |
| FastAPI async | https://fastapi.tiangolo.com/async/ |
| Starlette responses | https://www.starlette.dev/responses/ |
| Celery brokers | https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/index.html |
| Tantivy | https://github.com/quickwit-oss/tantivy |
| Tantivy Python bindings | https://github.com/quickwit-oss/tantivy-py |

Findings:

- Django admin is useful for model-centric internal CRUD, but RetOS needs process-centric workflows: jobs, OCR, indexing, agent timelines, and evidence ledgers.
- FastAPI and Starlette fit async endpoints and SSE well.
- Celery with RabbitMQ is justified for long-running retryable jobs.
- Tantivy provides a strong local BM25 engine without operating OpenSearch in the MVP.

Decisions:

- Backend: FastAPI.
- Frontend: React.
- Jobs: Celery with RabbitMQ.
- Streaming: Server-Sent Events.
- Search: Tantivy through an adapter.
