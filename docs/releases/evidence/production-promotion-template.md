# Production Promotion Evidence Template

Use this template for the human promotion review. Keep the completed copy with the
versioned release note or the release record for the target environment.

## Candidate

| Field | Value |
| --- | --- |
| Release version | `<version>` |
| Immutable release tag | `v<version>` |
| Commit SHA | `<full-sha>` |
| GitHub Actions run | `<url>` |
| Backend image digest | `sha256:<digest>` |
| Web image digest | `sha256:<digest>` |
| Previous image tag | `<previous-tag>` |
| Target environment | `<environment>` |
| Reviewer | `<name>` |
| Review date | `<YYYY-MM-DD>` |

## Machine Evidence

Paste or link the output for each gate:

- `make ci-status-check`
- `make check`
- `make dependency-audit`
- `make security-policy-check`
- `make ignore-hygiene-check`
- `make integration`
- `make frontend-test`
- `make frontend-e2e`
- `make frontend-visual-audit`
- `make docker-smoke`
- `make release-check`
- `make production-preflight`
- `make auditor-static-check`
- `make release-evidence-check`

## Release Provenance

- GHCR backend digest recorded:
- GHCR web digest recorded:
- SBOM/provenance attestation links:
- Cosign signature verification output:
- Image labels inspected:
- API, worker, and migrate share one backend image ID:

## Visual Review

- Desktop visual audit PNG reviewed:
- Mobile visual audit PNG reviewed:
- Visual reviewer:
- Visual review decision:
- UI issues accepted or filed:

## Backup And Restore Rehearsal

- Backup timestamp:
- Backup location:
- Backup artifact path:
- Postgres dump created:
- Storage archive created:
- Eval reports archive created:
- Eval datasets archive created:
- Restore rehearsed in disposable environment:
- Migrations rerun after restore:
- Health checks after restore:
- Index rebuild decision:

## Security Review

- Development secrets replaced:
- `RETOS_JWT_SECRET` rotated and stored securely:
- Bootstrap admin replaced or disabled:
- CORS origins reviewed:
- API/web/RabbitMQ/Postgres/Ollama exposure reviewed:
- Provider keys stored in secret manager:
- Paid-provider budget owner recorded:
- `/audit/export` hash-chain snapshot reviewed:

## Rollback

- Previous image tag:
- Rollback owner:
- Rollback command rehearsed:
- Data restore trigger criteria:
- Incident log location:

## Decision

- Promotion decision:
- Accepted scope limits:
- Required follow-up issues:
