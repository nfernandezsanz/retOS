# Release Notes

This directory stores versioned release notes and release-candidate notes. `CHANGELOG.md`
remains the running human-readable change log; files here are immutable release artifacts
for a specific version once a tag is cut.

Before a release leaves candidate status:

- The matching GitHub Actions run must be green.
- The GHCR release workflow must publish `retos-backend` and `retos-web`.
- SBOM/provenance, Cosign signature, and signature verification evidence must be linked or
  copied into the note.
- Migration and rollback notes must be explicit.
