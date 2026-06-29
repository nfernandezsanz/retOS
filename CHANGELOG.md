# Changelog

All notable RetOS changes are tracked here so release candidates can be reviewed without
reading every commit.

This project follows a pragmatic changelog format with an `Unreleased` section first.
Each shipped release should move entries into a dated version section and link the release
tag in GitHub.

## Unreleased

### Added

- `make local-demo` now gives first-time users the shortest local path: bootstrap safe
  environment defaults, run the doctor, start the Docker API/worker/web stack without
  pulling optional Ollama, seed the demo corpus, and print the useful URLs.
- File upload ingestion now rejects declared MIME/extension mismatches for `.txt`,
  `.md`, and `.pdf` uploads before writing bytes, and preserves declared
  `content_type` in job/document audit metadata.
- Human-readable audit handoff report generated from the JSON manifest, plus a local
  checker so the report preserves candidate, gate, blocker, hash, and visual evidence.
- Audit handoff reports now include a promotion decision checklist that separates
  locally proven evidence from external release and target-environment decisions.
- `make local-acceptance` now provides one local pre-audit gate across backend quality,
  API/browser integration, frontend build, visual audit, Docker config, auditor handoff,
  and Docker stack smoke.
- Audit manifests now hash the Markdown handoff exporter and checker so the human
  report path is covered by the same critical-file evidence as the JSON manifest.
- CI now publishes a `retos-audit-handoff-<commit>` Markdown artifact and the current
  HEAD CI status checker requires it alongside the JSON manifest and visual audit.
- Local auditor handoff bundles now package the JSON manifest, Markdown report,
  production/release docs, workflows, and checksum sidecar for offline review.
- Local auditor handoff bundles now include versioned calibration and calibration trend
  evidence so reviewers can inspect the dataset gate inputs offline.
- Auditor evidence matrix mapping the project objective to current evidence, local gates,
  and remaining external promotion blockers.
- Production readiness audit pack with explicit promotion blockers, human review order,
  acceptance checks, and a CI-enforced guard.
- Current-HEAD GitHub Actions status check for human release auditors.
- CI-enforced Python and Node dependency advisory audits, plus patched `orjson` and
  `Pillow` runtime pins.
- Focused branch coverage tests for ingestion, indexing, agent, audit, and dataset
  adapters, raising backend coverage evidence to 95.20% total and the CI branch
  ratchet to 90.44%.
- Nullable audit `trace_id` columns for journal/progress correlation, including default
  job-id traces for job-backed events and trace-aware audit export hashes.
- Durable audit hash-chain columns for journal/progress events, including migration
  backfill and export validation against persisted hash material.
- Provider catalog `missing_config` hints and runtime fail-fast checks so selected paid
  providers require both explicit cost opt-in and complete provider configuration.
- Audit export integrity metadata with canonical payload hashes and a chronological
  SHA-256 hash chain for offline review.
- React document evidence inspection for latest versions, artifacts, and searchable
  segments directly from the document inventory.
- Metric-gated real-dataset calibration manifests so release candidates can fail on
  explicit retrieval, citation, grounding, or budget thresholds.
- Offline `make eval-calibration-gate` validation for versioned calibration evidence,
  including required targets, sample sizes, metric gates, HTTPS provenance, and path
  safety.
- Offline `make eval-calibration-trend-gate` validation for versioned calibration trend
  evidence, including sample growth, required targets, metric regression tolerance,
  HTTPS provenance, and path safety.
- Local doctor now checks the active `.env` when present, failing unsafe production
  placeholders, wildcard CORS outside development, invalid providers, and short secrets.
- Standalone `make env-security-check` gate for active `.env` security validation without
  starting Docker, Node, or service probes.
- Standalone `make visual-audit-check` gate for local desktop/mobile visual-audit
  manifest, screenshot existence, byte-size, SHA-256, and viewport verification.
- Production promotion evidence template now requires `make env-security-check` and
  `make visual-audit-check` output alongside the human security and visual reviews.
- Standalone `make promotion-template-check` gate for required production promotion
  template sections, machine gates, release provenance, visual/security review,
  backup/restore rehearsal, rollback, and decision fields.
- Standalone `make backup-restore-drill-check` gate and evidence template for
  recording backup artifacts, disposable restore commands, health checks,
  audit-export validation, and promotion impact.
- Standalone `make target-security-review-check` gate and evidence template for
  target-environment auth, secrets, provider keys, CORS, exposed ports, release
  provenance, rollback, accepted risks, and promotion impact.
- Standalone `make calibration-scope-decision-check` gate and evidence template for
  recording bounded pilot scope acceptance or broader public-slice trend evidence before
  promotion.
- Opt-in real-dataset calibration runner that fetches or reuses bounded public SQuAD,
  HotpotQA, HotpotQA-agent, and NQ-Open adapter samples, writes per-suite reports, and
  emits a manifest with provenance, metrics, and report paths.
- Keyboard navigation hardening for the React console, including a skip link to the
  workspace, visible sidebar focus rings, and mobile browser coverage for provider,
  eval, and audit surfaces.
- Shared backend Docker runtime for API, worker, and migrations with topology and
  runtime image ID guards.
- Docker topology guard now fails if API and worker drift in application environment or
  persistent backend state volumes while sharing the backend image.
- CI now validates release workflow, release notes, versioned release notes, and static
  OCI image metadata before the Docker stack smoke run.
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
- Agent query plans now execute bounded multi-hop subqueries and accumulate unique
  evidence under citation, token, and search budgets.
- Deterministic agent multi-hop eval suite for query plans, bounded subqueries,
  evidence-route coverage, bridge terms, citations, grounding, and budgets.
- Expanded agent multi-hop calibration fixtures for invoice-retention and
  incident-escalation evidence routes, including strict citation-budget coverage.
- React local eval controls now run the built-in agent multi-hop eval and surface its
  metrics in the same result, history, trend, and audit workflow as other suites.
- React eval history now exposes the persisted regression gate with promote/block
  decisions, tolerances, and per-metric regression evidence.
- Persisted eval runs now expose a regression gate that normalizes metric direction,
  supports tolerances, and flags candidate calibration drops without provider calls.
- Dataset-backed eval runs can now be attached to a domain, filtered by domain in
  history/trends, rerun with the same scope, and guarded against mixed-scope comparisons.
- Viewers with explicit domain grants can now run dataset-backed evals, read
  domain-filtered eval history/trends, and rerun domain-scoped dataset eval jobs without
  gaining access to global evals or built-in evals.
- Viewers with explicit domain grants can now compare and regression-gate same-domain
  persisted eval runs when they pass the granted `domain_id`.
- Real-dataset calibration gates can now be scoped per target, fetched samples preserve
  ignored provenance sidecars, and manifests can be exported as path-safe Markdown
  release evidence.
- Real-dataset calibration manifests can now be compared as path-safe trend evidence
  with record/case growth checks, metric-regression tolerance, source URLs, and license
  provenance.
- React eval controls now expose an explicit `Eval scope` selector that attaches
  dataset-backed SQuAD, HotpotQA, Natural Questions, and OCR benchmark runs to a domain
  and filters history, trends, comparison, and regression-gate workflows.
- HotpotQA supporting facts can now be converted into a local `hotpotqa-agent` eval
  profile for deterministic agent query-plan, evidence-route, bridge-term, grounding,
  citation, and budget calibration through CLI, admin API, rerun, and React controls.
- Dataset fetch profiles now support retryable source mirrors and persist the effective
  `source_url`, giving real-dataset calibration runs clearer provenance when an
  official primary endpoint is unavailable.
- Dataset fetching now prioritizes configured HTTPS mirrors over HTTP primaries so
  public calibration does not stall on slow or insecure legacy dataset endpoints.
- Networked eval dataset fetches now use the bundled `certifi` CA store to avoid local
  Python certificate-store drift during opt-in real-dataset calibration.
- Tantivy search now falls back to a sanitized natural-language query when the native
  parser rejects punctuation from real user questions.
- The generic job retry endpoint now reruns failed or cancelled `eval.run` jobs through
  the eval harness, preserving `rerun_from_job_id` for audit traceability.
- API smoke now exercises generic retry for failed eval jobs and verifies the resulting
  rerun origin in persisted journal/progress events.
- Backend tests now generate `coverage.json` and CI enforces a separate branch coverage
  ratchet so branch coverage cannot regress while the project works toward the 90%
  branch-only target.
- Eval report artifact tests now cover path-safe report stem sanitization and JSON/Markdown
  writes, and coverage excludes type-only `Protocol` declarations from runtime branch
  accounting.
- RetOS now ships a project mark, README project card, favicon metadata, and documented
  brand tokens for the React audit console.

### Changed

- The React console now uses shorter headers, tighter bounded module scroll regions,
  native tooltip fallbacks on navigation pills, and hover tooltips preserved in audit
  summary panels so operational screens feel less like long pages.
- Audit manifests now hash the auditor evidence matrix and record its local gate so the
  machine-readable handoff preserves objective-to-evidence traceability.
- Audit manifests now hash the RetOS project card, favicon mark, frontend brand tokens,
  and visual-audit smoke test so brand evidence is part of the machine-readable handoff.
- README onboarding now uses live GitHub Actions status badges, action-oriented local
  workflow pills, and collapsible operator paths for try/audit/develop entry points.
- Local onboarding now includes an idempotent `make bootstrap-env` command that creates
  `.env` from `.env.example` without overwriting existing local secrets.
- The React eval runner now groups dataset-specific SQuAD, HotpotQA, Natural Questions,
  and OCR controls into compact tooltip-backed accordions so the quality screen starts
  shorter while keeping local execution controls one click away.
- The React console now keeps responsive context cards in horizontal strips on smaller
  screens, bounds the mobile document Library into separate scrollable sections, and
  keeps secondary query evidence collapsed behind tooltip-backed review sections.
- The React console now uses a more explicit audit-console brand treatment with a
  compact operating-posture band, stronger first-viewport identity, reduced-motion
  handling, and stable responsive heading sizing.
- SQLite-backed tests now close direct inspection connections deterministically so
  Python 3.14 resource warnings do not pollute local audit gates.
- HotpotQA and HotpotQA-agent calibration now use deterministic named-entity follow-up
  retrieval and a larger supporting-fact evidence budget, improving bounded public
  sample grounding and multi-hop support to PASS without provider calls.
- Release calibration evidence now records a 200-record public dataset sample with 40
  evaluated cases per target across SQuAD, HotpotQA, HotpotQA-agent, and NQ-Open adapter
  samples.
- Release calibration trend evidence now records a zero-regression PASS from
  100-record/30-case to 200-record/40-case public samples after hardening deterministic
  HotpotQA follow-up retrieval.
- Compose now builds the shared backend image only through the `api` service; `worker`
  and `migrate` reuse the same `retos-backend` tag instead of declaring parallel builds.
- Docker smoke now verifies API, worker, and migrations run the same backend image ID,
  then inspects built application image metadata and image size budgets before exercising
  the stack.

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
