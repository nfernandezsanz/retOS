# Backup And Restore Drill Evidence Template

Use this template for a local or target-environment backup/restore rehearsal. Keep the
completed copy with the production promotion evidence for the release candidate.

## Candidate

| Field | Value |
| --- | --- |
| Release version | `<version>` |
| Commit SHA | `<full-sha>` |
| Image tag | `<tag>` |
| Environment | `<local-or-target>` |
| Compose project | `<project>` |
| Operator | `<name>` |
| Drill date | `<YYYY-MM-DD>` |

## Backup Evidence

- Backup timestamp:
- Backup directory:
- Postgres dump path:
- Postgres dump size:
- Storage archive path:
- Storage archive size:
- Eval reports archive path:
- Eval reports archive size:
- Eval datasets archive path:
- Eval datasets archive size:
- Search index archive path:
- Search index archive size:
- Backup checksum command:
- Backup checksum output:

## Restore Evidence

- Disposable restore environment:
- Restore source backup:
- `docker compose stop api worker web` output:
- Postgres restore command:
- Postgres restore output:
- Storage restore output:
- Eval reports restore output:
- Eval datasets restore output:
- Search index restore output:
- `docker compose run --rm migrate migrate` output:
- `docker compose up -d api worker web` output:

## Health Evidence

- `curl --fail http://localhost:8000/healthz` output:
- `curl --fail http://localhost:8000/readyz` output:
- `curl --fail http://localhost:8000/versionz` output:
- `curl --fail http://localhost:8080/` output:
- `make api-smoke` output:
- `make audit-export-check EXPORT=retos-audit-export.json` output:
- Index rebuild decision:

## Audit Evidence

- `/audit/export` file:
- `/audit/export` head hash:
- Journal event count:
- Progress event count:
- Continuity gaps:
- Validation failures:

## Decision

- Drill result:
- Data loss observed:
- Rollback required:
- Follow-up issues:
- Promotion impact:
