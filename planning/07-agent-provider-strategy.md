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
