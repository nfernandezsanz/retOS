# Product Scope

## Goal

RetOS is an open source, Dockerized system for local document research with strong traceability. Users can manage domains, upload or mount documents, process them reproducibly, and ask cited questions through a local-first agentic runtime.

## Principles

| Principle | Practical Impact |
| --- | --- |
| Versioned source of truth | Raw files, document versions, artifacts, and anchors live in the corpus store. |
| Rebuildable indexes | Search indexes are projections and can be recreated. |
| Auditable by default | Ingestion, search, reading, citations, and answers produce journals and ledgers. |
| Local-first | Ollama with Gemma 4 works without paid providers. |
| Provider switching | OpenAI, Anthropic, Google, OpenRouter, Azure, and Ollama fit behind adapters. |
| Tests cost nothing | Default tests use fakes and mocks. |

## MVP Capabilities

- Manage domains and document sources.
- Upload files or register mounted folders.
- Ingest `.md`, `.txt`, `.pdf`, and OCR-backed PDFs/images.
- Persist raw files, artifacts, normalized text, metadata, segments, and anchors.
- Reindex incrementally with deterministic identities.
- Search with Tantivy BM25, path, metadata, and filters.
- Query through Deep Agents with controlled tools.
- Show answers with citations, evidence ledgers, and run timelines.
- Stream scan, OCR, indexing, and agent progress through SSE.
- Run with Docker Compose and persistent volumes.
- Maintain at least 90% total coverage and drive branch coverage to 90% with an
  explicit non-regression ratchet in CI.

## Non-Goals

- Do not make a vector database the source of truth.
- Do not rely on paid providers for tests or local development.
- Do not use Django admin or Jinja2 as the primary UI.
- Do not build the main agent loop with classic LangGraph in the MVP.
- Do not promise perfect PDF layout extraction in the first release.
