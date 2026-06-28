# Changelog

All notable RetOS changes are tracked here so release candidates can be reviewed without
reading every commit.

This project follows a pragmatic changelog format with an `Unreleased` section first.
Each shipped release should move entries into a dated version section and link the release
tag in GitHub.

## Unreleased

### Added

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

### Changed

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
