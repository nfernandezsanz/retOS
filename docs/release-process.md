# Release Process

RetOS releases should be boring, reproducible, and easy to audit. A release candidate is
ready only when the code, images, documentation, and validation evidence all point to the
same revision. Production promotion is a separate human decision tracked through
[docs/production-readiness.md](production-readiness.md).

## Versioning

Use immutable release tags. Pre-alpha builds may use dated tags while the public API is
still moving:

```bash
export RETOS_RELEASE_VERSION=2026.06.28-alpha.1
export RETOS_IMAGE_TAG="${RETOS_RELEASE_VERSION}"
export RETOS_VERSION="${RETOS_RELEASE_VERSION}"
export RETOS_REVISION="$(git rev-parse HEAD)"
export RETOS_CREATED="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
```

Do not use `latest` for shared environments. Local development may use the default
`local` tag.

## Release Candidate Checklist

1. Move relevant entries from `CHANGELOG.md#Unreleased` into a dated version section, or
   explicitly document why the candidate is still unreleased/pre-alpha.
2. Build traceable images:

```bash
docker compose build api web
RETOS_REQUIRE_BUILT_IMAGES=1 scripts/check_image_metadata.sh
RETOS_REQUIRE_BUILT_IMAGES=1 scripts/check_image_size.sh
```

3. Validate the publishing workflow contract:

```bash
scripts/check_release_workflow.sh
scripts/check_versioned_release_notes.sh
```

4. Run the complete local gate:

```bash
make release-check
make audit-pack-check
make production-preflight
make auditor-static-check
make auditor-handoff-check
make audit-manifest-check
make audit-manifest OUTPUT=evals/reports/audit-manifest.json
make audit-bundle OUTPUT=evals/reports/retos-audit-handoff.tar.gz AUDIT_MANIFEST_SKIP_CI=true
docker compose --env-file .env.example config
docker compose --dry-run build
make dependency-audit
make ci-status-check
make check
make integration
make frontend-test
make frontend-e2e
make frontend-visual-audit
make docker-smoke
```

5. Confirm GitHub Actions is green for the release commit with `make ci-status-check`.
6. Push a `v<version>` tag or run `.github/workflows/release.yml` manually to publish
   `retos-backend` and `retos-web` to GHCR with SBOM, provenance, Cosign signatures, and
   Cosign signature verification for both published digests. The workflow reruns backend
   format/lint/type/test/eval-smoke, Python and Node dependency audits, frontend build,
   browser smoke, visual audit with downloadable screenshots and hash metadata, release
   readiness, and production preflight before any image is pushed.
7. Copy the backend and web digests from the workflow summary, then verify the published
   evidence independently. The check verifies Cosign signatures and confirms each
   immutable version tag resolves to the recorded digest:

```bash
VERSION="${RETOS_RELEASE_VERSION}" \
BACKEND_DIGEST="sha256:<backend-digest>" \
WEB_DIGEST="sha256:<web-digest>" \
make release-evidence-check
```

8. Attach validation evidence to the GitHub release notes:

| Evidence | Required |
| --- | --- |
| Commit SHA | Yes |
| Image tags | Yes |
| OCI labels inspected | Yes |
| Backend coverage | Yes |
| Dependency audit | Yes |
| API smoke | Yes |
| Browser smoke | Yes |
| Visual audit screenshots | Yes |
| Compose config | Yes |
| Docker build dry run | Yes |
| Docker stack smoke | Yes |
| Image size budgets | Yes |
| GHCR publishing | Yes |
| SBOM/provenance | Yes |
| Cosign signatures and verification | Yes |
| `make release-evidence-check` output | Yes |
| `make audit-manifest-check` output | Yes |
| `make audit-manifest` JSON | Yes |
| `make audit-bundle` tarball and `.sha256` | Yes |
| Eval smoke | Yes |
| Migration notes | Yes |
| Rollback notes | Yes |
| Production promotion template | Yes |

Before production promotion, reconcile this release evidence with
[docs/production-readiness.md](production-readiness.md) and close or explicitly accept
every blocker there.
Use [docs/releases/evidence/production-promotion-template.md](releases/evidence/production-promotion-template.md)
for the final human promotion record.

## Release Notes Template

```markdown
# RetOS <version>

Commit: <sha>
Images:
- retos-backend:<version>
- retos-web:<version>

## Highlights

- ...

## Migration Notes

- ...

## Compatibility

- Python:
- Node:
- Postgres:
- RabbitMQ:
- Ollama:

## Security

- ...

## Validation

- Backend format/lint/typecheck/tests:
- Backend coverage:
- API smoke:
- Frontend build:
- Browser smoke:
- Docker topology:
- Backend runtime image ID:
- Image metadata:
- Image size budgets:
- GHCR publishing:
- SBOM/provenance:
- Cosign signatures and verification:
- Docker stack smoke:
- Eval smoke:

## Known Limitations

- ...

## Rollback

- ...
```

## Audit Expectations

- `CHANGELOG.md` stays human-readable and ordered newest first.
- `docs/releases/` stores versioned release notes or release-candidate notes with
  validation evidence, migration notes, known limitations, and rollback guidance.
- Every release note references the commit SHA and immutable image tags.
- Draft release notes may record a `Current draft evidence commit` that trails later
  documentation-only commits. That SHA is the code revision covered by the recorded
  gates, CI run, and audit artifacts; the immutable release tag commit must be
  reconciled with the note before promotion.
- Every release candidate records `scripts/check_image_size.sh` output or the equivalent
  `make image-size-check` evidence. Default budgets can be overridden with
  `RETOS_BACKEND_IMAGE_MAX_BYTES` and `RETOS_WEB_IMAGE_MAX_BYTES` only when the release
  notes explain the increase.
- `.github/workflows/release.yml` is the source of truth for publishing `retos-backend`
  and `retos-web` to GHCR. It must keep SBOM, provenance, Cosign signing, and Cosign
  signature verification enabled.
- The release workflow must run dependency audits plus browser/visual smoke before
  publishing images, and it must upload visual audit screenshots as release evidence.
- `make audit-manifest` exports a machine-readable local handoff manifest with the
  current commit, CI lookup, generation context, critical file hashes, visual audit
  screenshots, required gates, and remaining external promotion evidence. When generated
  inside GitHub Actions, the manifest is an in-run snapshot and must be paired with a
  later `make ci-status-check` success for the same commit.
- CI also exports `retos-audit-handoff-<commit>`, a Markdown companion generated from
  the same manifest snapshot for reviewers who prefer a readable handoff artifact. The
  report includes a promotion decision checklist that separates locally proven evidence
  from external release and target-environment decisions.
- `make audit-bundle` packages the local JSON manifest, Markdown handoff report,
  production readiness pack, release process, operations guide, branding guide, release
  note, promotion template, and workflow contracts into a tarball with a `.sha256`
  sidecar for offline auditor transfer.
- `make auditor-handoff-check` is the local auditor entry point for static guards,
  offline manifest export, and promotion preparation. It does not replace tag publishing,
  GHCR digests, SBOM/provenance, Cosign verification, or target-environment review.
- `scripts/check_published_release_evidence.sh` is the independent post-publish verifier
  for immutable image digests, Cosign signatures, and version tag-to-digest resolution.
  Run it through `make release-evidence-check` before final promotion evidence is
  accepted.
- CI validates release docs through `make release-check`.
- CI validates Python and Node dependency advisories before tests and browser smoke.
- CI validates the production readiness audit pack through `make audit-pack-check`.
- Operators use `docs/operations.md` for upgrade, backup, restore, and rollback.
