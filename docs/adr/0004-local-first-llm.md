# ADR 0004: Local-First LLM Runtime

## Status

Accepted

## Context

The system must run without spending money during development, tests, or local research.

## Decision

Use Ollama with `gemma4` as the default local model profile. Paid providers remain configurable but disabled by default.

## Consequences

- `RETOS_ALLOW_PAID_LLM=false` is the safe default.
- Live provider tests require explicit opt-in.
- Docker Compose includes Ollama, but model weights are not baked into the application image.
