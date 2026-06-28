# Changelog

All notable RetOS changes are tracked here so release candidates can be reviewed without
reading every commit.

This project follows a pragmatic changelog format with an `Unreleased` section first.
Each shipped release should move entries into a dated version section and link the release
tag in GitHub.

## Unreleased

### Added

- Shared backend Docker runtime for API, worker, and migrations with topology guards.
- OCI image metadata labels for backend and web images, including source, license,
  version, revision, and build timestamp.
- Release readiness checks for Docker topology, image metadata, safe local defaults, and
  operator runbook coverage.
- Deterministic agent evidence-route coverage that records segment, document, anchor,
  neighboring-context, and warning signals for each completed query.
- NQ-Open dataset fetch profile that converts real question samples into the local
  Natural Questions adapter shape for opt-in calibration without full corpus downloads.
- Image size guardrails for backend and web release images, including configurable byte
  budgets and Docker smoke enforcement.
- GHCR release workflow for backend and web images with SBOM/provenance attestation
  requests and Cosign keyless signing.
- Versioned release-candidate notes with validation evidence, pending publish evidence,
  known limitations, migration notes, and rollback guidance.
- Local source sampling for official simplified Natural Questions `.jsonl(.gz)` files,
  enabling full document-shape eval slices without CI network downloads.
- Deterministic multi-hop query audit that records whether multi-part questions have
  cross-document evidence and bridge terms.
- React query results now show multi-hop audit status, document breadth, warnings, and
  bridge terms.
- Eval reports now include dataset/source provenance metadata in JSON, Markdown, API
  responses, persisted job payloads, journal/progress events, and the React eval panel.
- Agent queries now persist and display deterministic query plans with strategy,
  subqueries, expected evidence breadth, planned steps, and operator warnings.

### Changed

- Docker smoke now inspects built application image metadata and image size budgets before
  exercising the stack.

### Security

- Release images remain traceable to the source repository and MIT license through
  `org.opencontainers.image.*` labels.

## Release Note Checklist

Before cutting a release, confirm the release notes include:

- Summary of user-facing changes.
- Migration notes, including whether Alembic migrations are required.
- Compatibility notes for Docker, Postgres, RabbitMQ, Ollama, and browser support.
- Security notes, especially authentication, provider-cost, and secret-handling changes.
- Validation evidence from CI, Docker smoke, API smoke, browser smoke, and eval smoke.
- Known limitations or rollback guidance.
