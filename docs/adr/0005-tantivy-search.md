# ADR 0005: Tantivy For BM25 Search

## Status

Accepted

## Context

RetOS needs strong lexical search while keeping indexes rebuildable and local-first.

## Decision

Use Tantivy through a search adapter as the default BM25 engine.

## Consequences

- The MVP avoids operating OpenSearch.
- Search remains a projection, not the source of truth.
- A future OpenSearch adapter can be added without changing the domain model.
