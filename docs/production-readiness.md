# Production Readiness Audit Pack

RetOS is not production-promoted yet. This pack is the human-auditor entry point for
deciding whether a release candidate can move from pre-alpha validation into a controlled
production pilot.

## Current Verdict

| Area | Status | Evidence |
| --- | --- | --- |
| Product maturity | Pre-alpha candidate | `planning/04-process-tracker.md` keeps phases 0-6 in progress. |
| CI health | Must be checked against current `HEAD` | `make ci-status-check` queries GitHub Actions for the current commit; `docs/releases/2026.06.28-alpha.1.md` records release-candidate evidence. |
| Backend coverage | Passing total and branch coverage | `README.md` records 95.26% total and 90.56% branch-only coverage. |
| Runtime topology | Guarded | `scripts/check_docker_topology.sh` and `scripts/check_backend_runtime_image.sh` protect the shared API/worker/migrate backend image model. |
| Dependency advisories | Guarded | `make dependency-audit` runs `pip-audit` and `npm audit --audit-level=high`; CI runs both checks. |
| Branding assets and UI contract | Guarded | `make brand-check` runs `scripts/check_branding_assets.sh` to validate project identity assets, palette tokens, README visibility, and Playwright brand smoke coverage. |
| Local cost safety | Guarded | `.env.example` keeps `RETOS_ALLOW_PAID_LLM=false`, `RETOS_PROVIDER=local`, and `RETOS_OLLAMA_MODEL=gemma4`. |
| Audit ledger | Implemented foundation | `docs/database.md` and `planning/06-auditability-journals.md` describe persisted journal/progress hash chains and export validation. |
| Release publishing | Not complete | GHCR digest, SBOM/provenance, and Cosign evidence are pending until the release workflow runs for a tag. |
| Final branch target | Complete | Branch coverage is ratcheted at 90.56%, above the 90% target. |

## Auditor Review Order

1. Confirm the candidate commit and the latest successful GitHub Actions run with
   `make ci-status-check`; then reconcile the release note under `docs/releases/`.
2. Run the local validation commands in `docs/release-process.md`.
3. Review `docs/operations.md` and `SECURITY.md` for upgrade, backup, restore, rollback,
   security defaults, reporting, and target-environment review.
4. Review `docs/docker.md` and the Compose output to confirm API, worker, and migrate use
   one backend image.
5. Inspect `planning/04-process-tracker.md` for current phase status and residual risks.
6. Open the React console and verify document management, long-running job progress,
   eval execution, query evidence, audit export, keyboard focus, and mobile layout.
7. Review a fresh `/audit/export` snapshot and validate the hash-chain fields.
8. Confirm no paid-provider calls are required for tests, eval smoke, browser smoke, API
   smoke, or Docker smoke.
9. Complete `docs/releases/evidence/production-promotion-template.md` or a copy of it
   for the target environment.

## Required Local Evidence

Run these commands from the repository root before asking for production promotion:

```bash
make local-acceptance
make check
make integration
make frontend-test
make frontend-e2e
make frontend-visual-audit
docker compose --env-file .env.example config
docker compose --dry-run build
make release-check
make production-preflight
make dependency-audit
make security-policy-check
make ignore-hygiene-check
make operations-runbook-check
make auditor-static-check
make auditor-handoff-check
make audit-manifest-check
make audit-manifest OUTPUT=evals/reports/audit-manifest.json
make audit-handoff-report MANIFEST=evals/reports/audit-manifest.json OUTPUT=evals/reports/audit-handoff.md
make audit-bundle OUTPUT=evals/reports/retos-audit-handoff.tar.gz AUDIT_MANIFEST_SKIP_CI=true
make audit-bundle-check
make audit-export-check
make release-notes-check
make versioned-release-notes-check
make docker-smoke
```

Remote repository evidence is separate from the local handoff. Run it when the current
GitHub Actions state must be attached to a promotion record:

```bash
make ci-status-check
```

For built release images, also run:

```bash
RETOS_REQUIRE_BUILT_IMAGES=1 scripts/check_image_metadata.sh
RETOS_REQUIRE_BUILT_IMAGES=1 scripts/check_image_size.sh
make docker-runtime-image-check
```

## Machine-Verified Preflight

The following gates are machine-verifiable before a human promotion review. They do not
replace the external registry evidence or the human security review, but they give the
auditor a stable local entry point:

| Area | Gate | Proves |
| --- | --- | --- |
| Local acceptance | `make local-acceptance` | Runs the local pre-audit acceptance path across backend quality, API/browser integration, frontend build, visual audit, Docker config, auditor handoff, and Docker stack smoke. |
| Backend quality | `make check` | Black, Ruff/PEP 8, mypy, 561 pytest cases, eval smoke, agent multi-hop eval, 95.26% total coverage, and 90.56% branch coverage. |
| HTTP and UI behavior | `make integration` | API smoke against real local endpoints plus Playwright browser smoke against the React console. |
| Frontend build | `make frontend-test` | TypeScript project build and Vite production bundle. |
| Browser and branding | `make frontend-e2e`, `make frontend-visual-audit`, and `make brand-check` | RetOS mark, palette, favicon, reduced motion, skip-link focus, responsive breakpoints, provider controls, end-to-end console workflows, reproducible desktop/mobile screenshots, and visual screenshot hash metadata. |
| Docker runtime | `make docker-smoke` | Built API/web images, Postgres, RabbitMQ, API, worker, migrate, web, HTTP smoke, worker-backed jobs, and one shared backend image ID. |
| Static release guardrails | `make release-check` | Required docs, Docker topology, image metadata source, image size budgets, workflow contract, release notes, audit pack, branding assets, safe defaults, and a dry-run of the published evidence verifier. |
| Production preflight | `make production-preflight` | Local evidence, branding, release docs, and external promotion blockers are aligned. |
| Dependency advisories | `make dependency-audit` | Python runtime and frontend lockfile dependency advisory checks pass without paid providers. |
| Security policy | `make security-policy-check` | Security reporting, secure defaults, human review scope, and operational links are aligned. |
| Ignore hygiene | `make ignore-hygiene-check` | Git and Docker contexts exclude secrets, generated files, local volumes, public datasets, reports, and backups. |
| Operations runbook | `make operations-runbook-check` | Backup, restore, rollback, health-check, audit-export, and promotion-evidence fields are aligned. |
| Auditor evidence matrix | `make auditor-evidence-matrix-check` | Objective requirements map to current evidence, local gates, and external promotion blockers in `docs/auditor-evidence-matrix.md`. |
| Auditor static pack | `make auditor-static-check` | Non-destructive dependency, security, ignore, operations, branding, release, preflight, and audit-pack guards pass together. |
| Auditor handoff | `make auditor-handoff-check` | Runs local static auditor gates and exports an offline audit manifest for the promotion record. |
| Audit manifest schema | `make audit-manifest-check` | Offline schema check for required manifest fields, gates, critical file hashes, visual artifact names, and external blockers. |
| Audit manifest | `make audit-manifest OUTPUT=evals/reports/audit-manifest.json` | JSON handoff with current commit, dirty state, generation context, coverage evidence derived from `backend/coverage.json`, required gates, critical file hashes including the auditor evidence matrix and branding assets, local visual screenshots, release artifact names, and remaining external promotion evidence. CI downloads the `retos-backend-coverage-<commit>` artifact before exporting `retos-audit-manifest-<commit>` as an in-run snapshot; treat that artifact as final evidence only with a later `make ci-status-check` success for the same commit. |
| Audit handoff report | `make audit-handoff-report MANIFEST=evals/reports/audit-manifest.json OUTPUT=evals/reports/audit-handoff.md` | Human-readable Markdown companion for the JSON manifest with candidate, verdict, coverage source, local gates, blockers, hashes, and visual evidence. CI also uploads `retos-audit-handoff-<commit>` from the same manifest snapshot for reviewers who want a readable artifact. |
| Audit handoff report schema | `make audit-handoff-report-check` | Offline check that the generated Markdown summary preserves key manifest evidence. |
| Promotion decision checklist | `make audit-handoff-report MANIFEST=evals/reports/audit-manifest.json OUTPUT=evals/reports/audit-handoff.md` | Generated checklist showing clean worktree, CI success, critical file hashes, local visual evidence, and remaining external promotion decisions. |
| Audit handoff bundle | `make audit-bundle OUTPUT=evals/reports/retos-audit-handoff.tar.gz AUDIT_MANIFEST_SKIP_CI=true` | Local tarball plus `.sha256` sidecar containing the JSON manifest, Markdown handoff, production readiness pack, release process, operations guide, branding guide, release note, promotion template, and CI/release workflows. |
| Audit handoff bundle schema | `make audit-bundle-check` | Offline check that the generated tarball has the required members and checksum. |
| Audit export verifier | `make audit-export-check` or `make audit-export-check EXPORT=retos-audit-export.json` | Self-tests the offline `/audit/export` verifier or validates a downloaded export by recomputing payload hashes, event hashes, continuity, head hash, and failure reasons. |
| Current HEAD CI | `make ci-status-check` | GitHub Actions has successful backend, frontend, docker, final audit-evidence jobs, and required backend-coverage/visual-audit/audit-manifest/audit-handoff artifacts for the current commit. |

## External Promotion Evidence

These items cannot be truthfully generated by local tests alone. They must be collected
from the release workflow, target operating environment, or human review before final
production promotion:

| Evidence | Source |
| --- | --- |
| GHCR digests | `.github/workflows/release.yml` run for the immutable release tag after dependency audits, browser smoke, and visual audit screenshots pass. |
| SBOM/provenance | GitHub Actions build attestations requested by the release workflow. |
| Cosign signature and tag verification | `make release-evidence-check` / `scripts/check_published_release_evidence.sh` run with the workflow summary's backend and web digests, verifying signatures and immutable version tag-to-digest resolution. |
| Broader calibration or accepted pilot scope | Additional public-slice trend evidence, or an explicit human acceptance of the bounded 200-record/40-case pilot scope. |
| Human security review | `SECURITY.md` target-environment review of auth, secrets, CORS, exposed ports, backups, provider keys, and rollback ownership. |

## Promotion Blockers

These items must be closed before a final production release:

| Blocker | Required Closure |
| --- | --- |
| GHCR publish evidence missing | Run `.github/workflows/release.yml` for the immutable release tag and record backend/web image digests. |
| SBOM/provenance evidence missing | Link or copy the attestation evidence from the release workflow into the versioned release note. |
| Cosign signature/tag evidence missing | Run `make release-evidence-check` with the published digests and record successful keyless signature verification plus version tag-to-digest resolution for both images. |
| Broader public calibration pending | Add trend evidence beyond the current 200-record/40-case public slices or document the pilot scope limit. |
| Human security review pending | Review auth, secrets, exposed ports, CORS, backup handling, and provider key handling for the target environment. |

## Production Pilot Acceptance Checklist

- [ ] Release note references the exact commit SHA under review.
- [ ] Latest GitHub Actions run is green for that SHA, including the final `audit-evidence` artifact job.
- [ ] `make ci-status-check` passes for the current `HEAD`.
- [ ] `make local-acceptance` passes against the candidate checkout.
- [ ] `make check` passes with no paid providers.
- [ ] `make dependency-audit` reports no known Python runtime advisories and no high-severity Node advisories.
- [ ] `make security-policy-check` passes.
- [ ] `make ignore-hygiene-check` passes.
- [ ] `make operations-runbook-check` passes.
- [ ] `make auditor-static-check` passes.
- [ ] `make auditor-handoff-check` passes and writes the offline audit manifest for the promotion record.
- [ ] `make audit-manifest-check` passes.
- [ ] `make audit-manifest OUTPUT=evals/reports/audit-manifest.json` was exported for the promotion record.
- [ ] `make audit-handoff-report MANIFEST=evals/reports/audit-manifest.json OUTPUT=evals/reports/audit-handoff.md` was exported for human review.
- [ ] `make audit-bundle OUTPUT=evals/reports/retos-audit-handoff.tar.gz AUDIT_MANIFEST_SKIP_CI=true` was exported with its `.sha256` sidecar.
- [ ] `make audit-export-check EXPORT=retos-audit-export.json` passed for a fresh target-environment `/audit/export` download.
- [ ] `make integration` passes against real local endpoints.
- [ ] `make frontend-test`, `make frontend-e2e`, and `make frontend-visual-audit` pass.
- [ ] Desktop and mobile visual audit PNGs were reviewed and accepted or tracked.
- [ ] `make docker-smoke` passes with API, worker, migrate, web, Postgres, RabbitMQ, and Ollama services.
- [ ] `scripts/check_release_readiness.sh` passes.
- [ ] `scripts/check_audit_pack.sh` passes.
- [ ] `make release-evidence-check` passes with published backend and web digests.
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
| Objective-to-evidence traceability | `docs/auditor-evidence-matrix.md`, `scripts/check_auditor_evidence_matrix.sh`, `make auditor-evidence-matrix-check` |
| Visual audit screenshots | `docs/branding.md`, `frontend/e2e/app.spec.ts`, `make frontend-visual-audit`, `frontend/visual-audit/manifest.json`, and the release workflow `retos-release-visual-audit-<commit>` artifact |
| Human visual review | `docs/releases/evidence/production-promotion-template.md` |
| Dependency advisory evidence | `scripts/check_dependency_audit.sh`, `make dependency-audit` |
| Security policy and human review | `SECURITY.md`, `scripts/check_security_policy.sh`, `make security-policy-check` |
| Ignore hygiene | `.gitignore`, `.dockerignore`, `scripts/check_ignore_hygiene.sh`, `make ignore-hygiene-check` |
| Operations runbook | `docs/operations.md`, `scripts/check_operations_runbook.sh`, `make operations-runbook-check` |
| Audit manifest schema | `scripts/check_audit_manifest.py`, `make audit-manifest-check` |
| Audit handoff report | `scripts/export_audit_handoff_report.py`, `scripts/check_audit_handoff_report.py`, `make audit-handoff-report` |
| Audit handoff bundle | `scripts/export_audit_bundle.py`, `scripts/check_audit_bundle.py`, `make audit-bundle` |
| Audit export verifier | `scripts/check_audit_export.py`, `make audit-export-check` |
| Current HEAD CI evidence | `scripts/check_ci_status.sh`, `make ci-status-check`, the `retos-backend-coverage-<commit>` artifact, the `retos-visual-audit-<commit>` artifact, the `retos-audit-manifest-<commit>` artifact, and the `retos-audit-handoff-<commit>` artifact |
| Audit handoff manifest | `scripts/export_audit_manifest.py`, `make audit-manifest` |
| Release procedure | `docs/release-process.md` |
| Operations runbooks | `docs/operations.md` |
| Docker topology | `docs/docker.md`, `docker-compose.yml`, `scripts/check_docker_topology.sh` |
| Runtime image parity | `scripts/check_backend_runtime_image.sh` |
| Versioned release notes | `docs/releases/` |
| Calibration evidence | `docs/releases/evidence/` |
| Promotion evidence template | `docs/releases/evidence/production-promotion-template.md` |
| Audit model | `planning/06-auditability-journals.md`, `docs/database.md` |
| Current project tracking | `planning/04-process-tracker.md` |
