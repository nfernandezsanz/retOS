# ADR 0002: FastAPI, React, And A Single Repository

## Status

Accepted

## Context

The product needs an operational UI with live indexing/OCR progress, query runs, evidence ledgers, and audit trails. Django admin was considered, but the core experience is process-centric rather than model-editing-centric.

## Decision

Use a single repository with:

- FastAPI for the API.
- React with TypeScript and Vite for the frontend.
- Server-Sent Events for live progress.

## Consequences

- The UI can focus on workflows instead of database tables.
- Async API endpoints and SSE are first-class implementation paths.
- Admin capabilities are implemented in the React console rather than Django admin.
