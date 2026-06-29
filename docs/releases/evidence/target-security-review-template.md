# Target Security Review Evidence Template

Use this template for the target-environment security review. Keep the completed copy
with the production promotion evidence for the release candidate.

## Candidate

| Field | Value |
| --- | --- |
| Release version | `<version>` |
| Immutable release tag | `v<version>` |
| Commit SHA | `<full-sha>` |
| Target environment | `<environment>` |
| Reviewer | `<name>` |
| Review date | `<YYYY-MM-DD>` |

## Auth And Access

- Admin users reviewed:
- Viewer users reviewed:
- Domain grants reviewed:
- Disabled accounts reviewed:
- Password reset procedure reviewed:
- Bootstrap admin replaced or disabled:
- JWT issuer reviewed:
- JWT audience reviewed:
- JWT expiry reviewed:
- Session/token revocation procedure reviewed:

## Secrets And Provider Keys

- `RETOS_JWT_SECRET` rotated and stored securely:
- `RETOS_BOOTSTRAP_ADMIN_PASSWORD` removed from target secrets:
- Database password stored in secret manager:
- RabbitMQ password stored in secret manager:
- Provider API keys stored in secret manager:
- Secret-manager owner:
- Secret rotation owner:
- Paid-provider opt-in reviewed:
- Paid-provider budget owner:
- Provider rollback plan:

## Network And Runtime Exposure

- API exposure reviewed:
- Web exposure reviewed:
- RabbitMQ exposure reviewed:
- Postgres exposure reviewed:
- Ollama exposure reviewed:
- CORS origins reviewed:
- TLS termination reviewed:
- Reverse proxy headers reviewed:
- Firewall rules reviewed:
- Docker network boundaries reviewed:

## Data Handling And Audit

- Mounted document sources reviewed:
- Upload storage reviewed:
- Eval datasets reviewed:
- Eval reports reviewed:
- `/audit/export` snapshot reviewed:
- Audit hash-chain validation output:
- Backup retention reviewed:
- Restore rehearsal evidence linked:
- Deletion policy reviewed:
- Sensitive-data handling decision:

## Release Provenance

- Current commit reviewed:
- GitHub Actions run reviewed:
- Backend image digest reviewed:
- Web image digest reviewed:
- SBOM/provenance reviewed:
- Cosign verification output reviewed:
- Image labels reviewed:
- API/worker/migrate shared image ID reviewed:

## Operations And Rollback

- Health checks reviewed:
- Docker smoke evidence reviewed:
- Upgrade procedure reviewed:
- Backup procedure reviewed:
- Restore procedure reviewed:
- Rollback owner:
- Previous image tag:
- Rollback command reviewed:
- Incident log location:
- Follow-up issue owner:

## Decision

- Security decision:
- Accepted risks:
- Required follow-up issues:
- Promotion impact:
