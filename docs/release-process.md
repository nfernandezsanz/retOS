# Release Process

RetOS releases should be boring, reproducible, and easy to audit. A release candidate is
ready only when the code, images, documentation, and validation evidence all point to the
same revision.

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
```

3. Run the complete local gate:

```bash
make release-check
make check
make integration
make frontend-test
make frontend-e2e
make docker-smoke
```

4. Confirm GitHub Actions is green for the release commit.
5. Attach validation evidence to the GitHub release notes:

| Evidence | Required |
| --- | --- |
| Commit SHA | Yes |
| Image tags | Yes |
| OCI labels inspected | Yes |
| Backend coverage | Yes |
| API smoke | Yes |
| Browser smoke | Yes |
| Docker stack smoke | Yes |
| Eval smoke | Yes |
| Migration notes | Yes |
| Rollback notes | Yes |

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
- Image metadata:
- Docker stack smoke:
- Eval smoke:

## Known Limitations

- ...

## Rollback

- ...
```

## Audit Expectations

- `CHANGELOG.md` stays human-readable and ordered newest first.
- Every release note references the commit SHA and immutable image tags.
- CI validates release docs through `make release-check`.
- Operators use `docs/operations.md` for upgrade, backup, restore, and rollback.
