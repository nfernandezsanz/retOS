# Production Readiness Audit Pack

RetOS is not production-promoted yet. This pack is the human-auditor entry point for
deciding whether a release candidate can move from pre-alpha validation into a controlled
production pilot.

## Current Verdict

| Area | Status | Evidence |
| --- | --- | --- |
| Product maturity | Pre-alpha candidate | `planning/04-process-tracker.md` keeps phases 0-6 in progress. |
| CI health | Must be checked against current `HEAD` | `make ci-status-check` queries GitHub Actions for the current commit; `docs/releases/2026.06.28-alpha.1.md` records release-candidate evidence. |
| Backend coverage | Passing total coverage, branch ratchet in progress | `README.md` records 93.54% total and 86.79% branch-only coverage. |
| Runtime topology | Guarded | `scripts/check_docker_topology.sh` and `scripts/check_backend_runtime_image.sh` protect the shared API/worker/migrate backend image model. |
| Dependency advisories | Guarded | `make dependency-audit` runs `pip-audit` and `npm audit --audit-level=high`; CI runs both checks. |
| Branding assets and UI contract | Guarded | `make brand-check` runs `scripts/check_branding_assets.sh` to validate project identity assets, palette tokens, README visibility, and Playwright brand smoke coverage. |
| Local cost safety | Guarded | `.env.example` keeps `RETOS_ALLOW_PAID_LLM=false`, `RETOS_PROVIDER=local`, and `RETOS_OLLAMA_MODEL=gemma4`. |
| Audit ledger | Implemented foundation | `docs/database.md` and `planning/06-auditability-journals.md` describe persisted journal/progress hash chains and export validation. |
| Release publishing | Not complete | GHCR digest, SBOM/provenance, and Cosign evidence are pending until the release workflow runs for a tag. |
| Final branch target | Not complete | Branch coverage is ratcheted at 86.79%; the target remains 90%. |

## Auditor Review Order

1. Confirm the candidate commit and the latest successful GitHub Actions run with
   `make ci-status-check`; then reconcile the release note under `docs/releases/`.
2. Run the local validation commands in `docs/release-process.md`.
3. Review `docs/operations.md` for upgrade, backup, restore, rollback, and security
   defaults.
4. Review `docs/docker.md` and the Compose output to confirm API, worker, and migrate use
   one backend image.
5. Inspect `planning/04-process-tracker.md` for current phase status and residual risks.
6. Open the React console and verify document management, long-running job progress,
   eval execution, query evidence, audit export, keyboard focus, and mobile layout.
7. Review a fresh `/audit/export` snapshot and validate the hash-chain fields.
8. Confirm no paid-provider calls are required for tests, eval smoke, browser smoke, API
   smoke, or Docker smoke.

## Required Local Evidence

Run these commands from the repository root before asking for production promotion:

```bash
make check
make integration
make frontend-test
make frontend-e2e
docker compose --env-file .env.example config
docker compose --dry-run build
make release-check
make dependency-audit
make ci-status-check
make release-notes-check
make versioned-release-notes-check
make docker-smoke
```

For built release images, also run:

```bash
RETOS_REQUIRE_BUILT_IMAGES=1 scripts/check_image_metadata.sh
RETOS_REQUIRE_BUILT_IMAGES=1 scripts/check_image_size.sh
make docker-runtime-image-check
```

## Promotion Blockers

These items must be closed before a final production release:

| Blocker | Required Closure |
| --- | --- |
| GHCR publish evidence missing | Run `.github/workflows/release.yml` for the immutable release tag and record backend/web image digests. |
| SBOM/provenance evidence missing | Link or copy the attestation evidence from the release workflow into the versioned release note. |
| Cosign signature evidence missing | Record successful keyless signature verification for both published image digests. |
| Branch coverage below final target | Raise the branch coverage ratchet to 90% or document an accepted release exception. |
| Broader public calibration pending | Add trend evidence beyond the current 200-record/40-case public slices or document the pilot scope limit. |
| Human security review pending | Review auth, secrets, exposed ports, CORS, backup handling, and provider key handling for the target environment. |

## Production Pilot Acceptance Checklist

- [ ] Release note references the exact commit SHA under review.
- [ ] Latest GitHub Actions run is green for that SHA.
- [ ] `make ci-status-check` passes for the current `HEAD`.
- [ ] `make check` passes with no paid providers.
- [ ] `make dependency-audit` reports no known Python runtime advisories and no high-severity Node advisories.
- [ ] `make integration` passes against real local endpoints.
- [ ] `make frontend-test` and `make frontend-e2e` pass.
- [ ] `make docker-smoke` passes with API, worker, migrate, web, Postgres, RabbitMQ, and Ollama services.
- [ ] `scripts/check_release_readiness.sh` passes.
- [ ] `scripts/check_audit_pack.sh` passes.
- [ ] Image labels include source, documentation, license, version, revision, and creation time.
- [ ] API, worker, and migrate use the same backend image ID.
- [ ] `.env.example` remains local-safe and contains only development placeholders.
- [ ] Backup and restore commands were rehearsed against a disposable environment.
- [ ] `/audit/export` validates hash-chain fields for journal and progress events.
- [ ] Operator has recorded rollback steps and previous image tag.
- [ ] GHCR digests, SBOM/provenance, and Cosign signature evidence are recorded.

## Evidence Locations

| Evidence | Location |
| --- | --- |
| Quality gates and commands | `README.md`, `Makefile`, `.github/workflows/ci.yml` |
| Dependency advisory evidence | `scripts/check_dependency_audit.sh`, `make dependency-audit` |
| Current HEAD CI evidence | `scripts/check_ci_status.sh`, `make ci-status-check` |
| Release procedure | `docs/release-process.md` |
| Operations runbooks | `docs/operations.md` |
| Docker topology | `docs/docker.md`, `docker-compose.yml`, `scripts/check_docker_topology.sh` |
| Runtime image parity | `scripts/check_backend_runtime_image.sh` |
| Versioned release notes | `docs/releases/` |
| Calibration evidence | `docs/releases/evidence/` |
| Audit model | `planning/06-auditability-journals.md`, `docs/database.md` |
| Current project tracking | `planning/04-process-tracker.md` |
