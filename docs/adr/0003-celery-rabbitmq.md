# ADR 0003: Celery With RabbitMQ

## Status

Accepted

## Context

RetOS has long-running, retryable workloads: scanning, hashing, OCR, PDF extraction, segmenting, indexing, eval runs, and agent runs.

## Decision

Use Celery with RabbitMQ as the broker. Postgres remains the durable record for job state, progress events, journals, and ledgers.

## Consequences

- RabbitMQ handles work distribution and retries.
- Workers pass lightweight commands and identifiers, not document payloads.
- Tests use eager/fake execution by default; broker-backed integration tests are opt-in.
