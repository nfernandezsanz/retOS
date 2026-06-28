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

### Changed

- Docker smoke now inspects built application image metadata before exercising the stack.

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
