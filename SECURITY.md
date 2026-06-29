# Security Policy

RetOS is pre-alpha software. Do not expose a deployment to untrusted users until the
production readiness checklist in `docs/production-readiness.md` and the human review
items below are complete for the target environment.

## Reporting

Please report security issues privately through GitHub Security Advisories when available.

## Supported Versions

Security review currently targets the active `main` branch and immutable release-candidate
tags documented under `docs/releases/`. Older local development snapshots are not supported
for security fixes.

## Defaults

- Paid LLM calls are disabled by default.
- Production requires a strong JWT secret.
- The development bootstrap admin password is rejected in production.
- Passwords are hashed with Argon2.
- CORS origins must be explicit outside development.
- Tests, smoke checks, browser checks, and eval smoke must not require paid providers.
- Provider readiness must expose missing configuration names, never provider key values.

## Sensitive Data

Do not include secrets, raw document contents, or personal data in issue reports unless the maintainer explicitly requests a sanitized sample.

## Production Human Review

Before production promotion, a human operator must record evidence for:

- Auth: admin and viewer roles, domain grants, JWT issuer/audience/expiry, account disable,
  password reset, and bootstrap admin replacement.
- Secrets: `RETOS_JWT_SECRET`, bootstrap credentials, provider API keys, database password,
  RabbitMQ password, and deployment secret-manager ownership.
- Network exposure: API, web, RabbitMQ, Postgres, Ollama, CORS origins, TLS termination,
  firewall rules, and any reverse proxy.
- Cost controls: `RETOS_ALLOW_PAID_LLM`, selected provider profile, budget owner, and
  rollback path if paid calls are enabled accidentally.
- Data handling: mounted document sources, uploaded files, eval datasets, eval reports,
  `/audit/export` snapshots, backup retention, restore rehearsal, and deletion policy.
- Release provenance: current commit, GitHub Actions run, GHCR digests, SBOM/provenance,
  Cosign signature verification, image labels, and shared API/worker/migrate image ID.
- Operations: upgrade, backup, restore, health checks, Docker smoke, rollback owner, and
  incident log location.

Use `docs/releases/evidence/target-security-review-template.md` to capture the completed
target-environment review, then keep that completed copy with the production promotion
evidence for the release candidate.

## Machine Guards

Run these before asking a human to approve a production pilot:

```bash
make local-acceptance
make security-policy-check
make target-security-review-check
make dependency-audit
make release-check
make production-preflight
make ci-status-check
```

These commands do not replace human review of the target environment, but they keep the
repository defaults, docs, release contracts, dependency advisories, and audit pack aligned.
