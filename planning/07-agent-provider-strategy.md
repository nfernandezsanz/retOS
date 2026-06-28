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
implementation uses controlled corpus tools (`search_corpus`, `read_citation`,
`map_sources`, and `inspect_evidence_table`) over already-indexed domain evidence,
builds a grounded answer from retrieved segments, persists citations, `evidence_audit`,
`contradiction_audit`, deterministic `multi_hop_audit`, deterministic `query_plan`,
deterministic `evidence_route`, and bounded adjacent
`neighbor_context` under
`job.payload.result`, enforces query budgets for searches, citations, neighboring
context, evidence tokens, and runtime, and writes `agent.queued`, `agent.started`,
`agent.completed`, or `agent.failed` progress/journal events. Usage is persisted with
`search_count`, `citation_count`, `evidence_tokens`, `runtime_ms`, and `within_budget`.

The Deep Agents harness factory is present through `deepagents.create_deep_agent` with a
RetOS-specific system prompt and a registered RetOS harness profile that excludes
Deep Agents filesystem and shell built-ins for the local `ollama:gemma4` profile.
`RETOS_AGENT_RUNTIME=deepagents` invokes that harness with the controlled corpus tools
after a bounded seed search. `RETOS_AGENT_RUNTIME=deterministic`
remains the default so CI, Docker smoke, and local development do not require downloaded
model weights or paid provider calls. The post-answer evidence audit appends a final
ledger when the model does not explicitly cite returned segment ids. The contradiction
audit flags opposite-polarity citation pairs for operator review. The deterministic
`multi_hop_audit` flags multi-part questions, checks whether citations span multiple
documents, and records cross-document bridge terms so operators can spot narrow answers
to broad questions. The deterministic `query_plan` runs before synthesis, records the
search/read/route/audit intent, executes bounded subqueries only for multi-hop plans,
deduplicates evidence under citation/token/search budgets, and is passed into the Deep
Agents seed payload with the executed `planned_searches` for the same auditable plan in
deterministic and agentic runtimes.
The Deep Agents harness now registers named `evidence_checker` and
`contradiction_checker` subagents with the same controlled RetOS corpus tools. The
`source_mapper` and `table_inspector` runtime roles are served by `map_sources` and
`inspect_evidence_table`, while `evidence_route` gives operators a deterministic coverage
view across citations, documents, anchors, and neighboring context. Richer multi-hop
planning can now build on persisted query-plan and multi-hop audit signals instead of
starting from an unstructured answer.
