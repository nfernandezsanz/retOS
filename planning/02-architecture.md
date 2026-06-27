# Architecture

## Overview

```text
documents / uploads / mounts
  -> versioned corpus store
  -> reproducible ingest pipeline
  -> OCR, normalized text, artifacts, segments, anchors
  -> rebuildable Tantivy BM25 and metadata indexes
  -> Deep Agents research runtime
  -> cited answer, evidence ledger, audit journal, traces
```

## Components

| Component | Responsibility |
| --- | --- |
| `web` | React console for domains, documents, jobs, queries, and evidence. |
| `api` | FastAPI REST/SSE API, auth, validation, orchestration. |
| `agent-worker` | Deep Agents runtime and controlled corpus tools. |
| `indexer-worker` | Scan, hash, extract, OCR, normalize, segment, and index. |
| `postgres` | Catalog, jobs, sessions, journals, ledgers, manifests. |
| `rabbitmq` | Celery broker for long-running jobs. |
| `search-index` | Tantivy indexes stored as rebuildable projections. |
| `ollama` | Local LLM runtime for `gemma4`. |

## Conceptual Data Model

| Entity | Key Fields |
| --- | --- |
| `domain` | `id`, `name`, `description`, `default_filters`, `created_at` |
| `source` | `id`, `domain_id`, `type`, `root_path`, `config_hash`, `status` |
| `document` | `id`, `source_id`, `canonical_path`, `mime_type`, `deleted_at` |
| `document_version` | `id`, `document_id`, `content_sha256`, `size`, `mtime`, `parser_profile`, `status` |
| `artifact` | `id`, `document_version_id`, `kind`, `path`, `sha256`, `metadata` |
| `segment` | `id`, `document_version_id`, `segment_sha256`, `anchor`, `page_start`, `page_end`, `text`, `metadata` |
| `index_manifest` | `id`, `document_version_id`, `indexer_version`, `chunker_config_hash`, `status` |
| `agent_run` | `id`, `session_id`, `trace_id`, `question`, `status`, `cost_estimate` |
| `journal_event` | `id`, `trace_id`, `event_type`, `actor`, `payload`, `prev_hash`, `event_hash` |
| `progress_event` | `id`, `job_id`, `event_type`, `payload`, `created_at`, `sequence` |

## Deterministic Identity Rules

```text
document_identity = source_id + canonical_path
content_identity = sha256(raw_bytes)
processing_identity = sha256(content_sha256 + parser_version + parser_config + chunk_config)
segment_identity = sha256(document_version_id + anchor + normalized_text)
```

## Agent Tool Boundary

The agent never reads the host filesystem directly. It operates through tools:

- `list_domains`
- `list_files`
- `search`
- `grep`
- `read_segment`
- `read_page`
- `neighbors`
- `inspect_table`
- `open_page_image`
- `cite`

## Patterns

| Pattern | Use |
| --- | --- |
| Hexagonal architecture | Keep domain logic independent from frameworks and SDKs. |
| Repository + Unit of Work | Make persistence transactional and testable. |
| Strategy | Swap LLM providers, parsers, indexers, and scorers. |
| Command | Model jobs and retries. |
| Adapter | Isolate external SDKs and engines. |
| Append-only journal | Preserve auditability and reproducibility. |
