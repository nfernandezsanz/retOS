# Operations Runbook

This runbook covers the Docker-first operating path for RetOS. It assumes the
application runs through `docker compose` with Postgres, RabbitMQ, Ollama, API,
worker, web, and the one-shot migration service.

## Release Images

RetOS publishes two application images per release:

| Image | Built By | Runtime Role |
| --- | --- | --- |
| `retos-backend:${RETOS_IMAGE_TAG}` | `backend/Dockerfile` target `backend-runtime` through the `api` Compose build | API, worker, and migrate commands from the same image. |
| `retos-web:${RETOS_IMAGE_TAG}` | `frontend/Dockerfile` | Static React console served by Nginx. |

The backend image must stay shared. `api`, `worker`, and `migrate` must resolve to
the same `retos-backend` image and differ only by command:

```bash
RETOS_IMAGE_TAG=2026.06.28 docker compose build api web
RETOS_IMAGE_TAG=2026.06.28 docker compose --env-file .env.example config
scripts/check_docker_topology.sh
```

Application images must also carry `org.opencontainers.image.*` OCI metadata labels for
source, documentation, license, version, revision, and build creation time:

```bash
RETOS_VERSION=2026.06.28 \
RETOS_REVISION="$(git rev-parse HEAD)" \
RETOS_CREATED="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
RETOS_IMAGE_TAG=2026.06.28 \
docker compose build api web

RETOS_REQUIRE_BUILT_IMAGES=1 RETOS_IMAGE_TAG=2026.06.28 scripts/check_image_metadata.sh
RETOS_REQUIRE_BUILT_IMAGES=1 RETOS_IMAGE_TAG=2026.06.28 scripts/check_image_size.sh
```

The default release budgets are `RETOS_BACKEND_IMAGE_MAX_BYTES=1400000000` and
`RETOS_WEB_IMAGE_MAX_BYTES=200000000`. Increase those limits only when the release notes
explain the dependency or asset change that makes the larger image intentional.

Release images are published by `.github/workflows/release.yml` to GHCR as
`retos-backend` and `retos-web`. The workflow requests SBOM and max-mode provenance
attestations during the image builds, then signs the published digests with Cosign
keyless signing. The workflow reruns backend and frontend gates before the publish job.
Verify `scripts/check_release_workflow.sh` before cutting a tag so the registry
publishing and signing contract stays aligned with the docs.

Before tagging a release candidate, run:

```bash
make release-check
make check
make integration
make frontend-test
make frontend-e2e
make docker-smoke
```

Use [docs/release-process.md](release-process.md) and [CHANGELOG.md](../CHANGELOG.md)
to prepare the human release notes, migration notes, validation evidence, and rollback
summary before publishing a tag.

Use immutable image tags for shared environments. Avoid `local` and `latest` outside a
developer workstation.

## Upgrade Runbook

1. Read the release notes and migration notes for the target version.
2. Create a backup before changing images.
3. Set the target tag:

```bash
export RETOS_IMAGE_TAG=2026.06.28
```

4. Validate configuration without mutating state:

```bash
docker compose --env-file .env config
scripts/check_docker_topology.sh
```

5. Pull or build the release images:

```bash
docker compose pull api web || docker compose build api web
```

6. Apply migrations through the release backend image:

```bash
docker compose run --rm migrate migrate
```

7. Restart the runtime services:

```bash
docker compose up -d api worker web
```

8. Run health and smoke checks. If a check fails, keep the backup, capture logs, and
rollback to the previous `RETOS_IMAGE_TAG`.

## Backup Runbook

Back up the canonical state, not rebuildable projections alone. The minimum useful
backup contains:

| State | Source | Notes |
| --- | --- | --- |
| Postgres catalog | `postgres` service | Domains, documents, artifacts, segments, jobs, progress events, audit journals, users, and eval metadata. |
| Storage volume | `retos_storage` | Uploaded files and mounted corpus material copied into managed storage. |
| Eval reports | `retos_eval_reports` | Exported JSON/Markdown reports. |
| Eval datasets | `retos_eval_datasets` | Optional local benchmark slices. |
| Search index | `retos_index` | Rebuildable from segments, but useful for faster restore. |

Example local backup:

```bash
backup_dir="backups/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "${backup_dir}"

docker compose exec -T postgres \
  pg_dump --format=custom --username=retos --dbname=retos \
  > "${backup_dir}/postgres.dump"

docker run --rm \
  -v retos_retos_storage:/data:ro \
  -v "$(pwd)/${backup_dir}:/backup" \
  alpine tar -C /data -czf /backup/storage.tgz .

docker run --rm \
  -v retos_retos_eval_reports:/data:ro \
  -v "$(pwd)/${backup_dir}:/backup" \
  alpine tar -C /data -czf /backup/eval-reports.tgz .

docker run --rm \
  -v retos_retos_eval_datasets:/data:ro \
  -v "$(pwd)/${backup_dir}:/backup" \
  alpine tar -C /data -czf /backup/eval-datasets.tgz .

docker run --rm \
  -v retos_retos_index:/data:ro \
  -v "$(pwd)/${backup_dir}:/backup" \
  alpine tar -C /data -czf /backup/index.tgz .
```

Use the actual Compose project prefix if it differs from the default `retos`.

## Restore Runbook

Restore into a stopped stack or a fresh Compose project. Do not restore over a running
API/worker pair.

1. Stop application services:

```bash
docker compose stop api worker web
```

2. Restore Postgres:

```bash
docker compose exec -T postgres dropdb --if-exists --username=retos retos
docker compose exec -T postgres createdb --username=retos retos
docker compose exec -T postgres \
  pg_restore --clean --if-exists --username=retos --dbname=retos \
  < backups/<timestamp>/postgres.dump
```

3. Restore volumes:

```bash
docker run --rm -v retos_retos_storage:/data -v "$(pwd)/backups/<timestamp>:/backup" \
  alpine sh -lc 'rm -rf /data/* && tar -C /data -xzf /backup/storage.tgz'
docker run --rm -v retos_retos_eval_reports:/data -v "$(pwd)/backups/<timestamp>:/backup" \
  alpine sh -lc 'rm -rf /data/* && tar -C /data -xzf /backup/eval-reports.tgz'
docker run --rm -v retos_retos_eval_datasets:/data -v "$(pwd)/backups/<timestamp>:/backup" \
  alpine sh -lc 'rm -rf /data/* && tar -C /data -xzf /backup/eval-datasets.tgz'
docker run --rm -v retos_retos_index:/data -v "$(pwd)/backups/<timestamp>:/backup" \
  alpine sh -lc 'rm -rf /data/* && tar -C /data -xzf /backup/index.tgz'
```

4. Re-run migrations for the active image, then start services:

```bash
docker compose run --rm migrate migrate
docker compose up -d api worker web
```

5. Run health checks and rebuild indexes from the UI/API if the restored index volume was
omitted or intentionally discarded.

## Health And Smoke Checks

Use these checks after deploys, restores, and upgrades:

```bash
curl --fail http://localhost:8000/healthz
curl --fail http://localhost:8080/
docker compose ps
docker compose logs --tail 100 api worker migrate
```

For a full disposable-stack validation:

```bash
make docker-smoke
```

For a live local API smoke with fake providers and no paid calls:

```bash
make api-smoke
```

## Operational Security Checklist

- Replace every development password from `.env.example` before exposing the stack.
- Set a unique `RETOS_JWT_SECRET` with at least 32 characters.
- Keep `RETOS_ALLOW_PAID_LLM=false` unless paid-provider use is intentional and budgeted.
- Store provider API keys only in `.env` or the deployment secret manager.
- Keep RabbitMQ and Postgres ports private unless an operator explicitly needs access.
- Back up Postgres and storage before image upgrades or schema migrations.
- Treat `evals/datasets` as operator-provided data; do not commit downloaded datasets.
- Verify `scripts/check_docker_topology.sh` before release so worker and API cannot drift.
- Verify `scripts/check_image_metadata.sh` before release so images remain traceable to source and license.

## Rollback Notes

Rollback is image-tag based:

```bash
export RETOS_IMAGE_TAG=<previous-tag>
docker compose up -d api worker web
```

If the failed upgrade applied irreversible schema changes, restore the backup captured
before the upgrade. Keep logs from the failed image for audit and regression tests.
