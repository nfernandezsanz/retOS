# Agent And Provider Strategy

## Runtime Decision

RetOS uses `deepagents.create_deep_agent` as the agentic runtime entrypoint. Classic LangGraph workflows are not used for the primary agent loop in the MVP.

## Agent Responsibilities

- Plan the query.
- Search BM25, metadata, and paths.
- Read enough evidence.
- Expand neighboring context.
- Register citations.
- Abstain when evidence is missing.
- Produce an answer and evidence ledger.
- Respect budgets.

## Subagents

| Subagent | Purpose |
| --- | --- |
| `source_mapper` | Explore candidate documents. |
| `evidence_checker` | Verify claims against citations. |
| `contradiction_checker` | Find contradictory evidence. |
| `table_inspector` | Inspect table artifacts. |

## Provider Profiles

| Profile | Default Model | Use |
| --- | --- | --- |
| `fake` | `fake:deterministic` | Tests. |
| `local` | `ollama:gemma4` | Local development and default use. |
| `openai` | Env configured | Explicit opt-in. |
| `anthropic` | Env configured | Explicit opt-in. |
| `google` | Env configured | Explicit opt-in. |
| `openrouter` | Env configured | Explicit opt-in. |
| `azure` | Env configured | Explicit opt-in. |

## Default Budgets

| Budget | Default |
| --- | --- |
| `max_searches` | 8 |
| `max_grep_calls` | 4 |
| `max_reads` | 20 |
| `max_pages` | 12 |
| `max_tokens_evidence` | 16000 |
| `max_runtime_seconds` | 120 |
| `max_subagents` | 3 |

Paid providers remain disabled by default.

## Provider Discovery Contract

The backend exposes `GET /llm/providers` for authenticated admins. The endpoint returns
only safe metadata:

- Active provider name, model, paid/free flag, and whether calls are allowed.
- Available profiles and whether each profile is configured and enabled.
- A human-readable disabled reason when configuration or cost opt-in is missing.

The endpoint never returns API keys and never performs a model call. This gives the UI a
safe way to render provider switches and warnings before the Deep Agents runtime is
connected.

## Implemented Query Contract

`POST /domains/{domain_id}/queries` creates a durable `agent.query` job. The current
implementation searches the domain BM25 index, builds a grounded answer from retrieved
segments, persists citations under `job.payload.result`, enforces query budgets for
searches, citations, evidence tokens, and runtime, and writes `agent.queued`,
`agent.started`, `agent.completed`, or `agent.failed` progress/journal events. Usage is
persisted with `search_count`, `citation_count`, `evidence_tokens`, `runtime_ms`, and
`within_budget`.

The Deep Agents harness factory is present through `deepagents.create_deep_agent` with a
RetOS-specific system prompt. Full model invocation, controlled tool execution,
subagent execution, and evidence-checking middleware remain future runtime slices.
