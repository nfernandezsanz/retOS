#!/usr/bin/env bash
set -euo pipefail

fail() {
  echo "Published release evidence failed: $1" >&2
  exit 1
}

require_value() {
  local name="$1"
  local value="$2"
  [[ -n "${value}" ]] || fail "${name} is required"
}

validate_digest() {
  local name="$1"
  local digest="$2"
  [[ "${digest}" =~ ^sha256:[0-9a-f]{64}$ ]] || fail "${name} must look like sha256:<64 lowercase hex chars>"
}

validate_version() {
  local version="$1"
  [[ "${version}" =~ ^[0-9]{4}\.[0-9]{2}\.[0-9]{2}([-._+a-zA-Z0-9]+)?$ ]] || fail "VERSION must look like 2026.06.28 or 2026.06.28-alpha.1"
  [[ "${version}" != "local" && "${version}" != "latest" ]] || fail "VERSION must be immutable, not ${version}"
}

VERSION="${VERSION:-${RETOS_RELEASE_VERSION:-}}"
REGISTRY="${REGISTRY:-ghcr.io}"
REPOSITORY_OWNER="${REPOSITORY_OWNER:-${GITHUB_REPOSITORY_OWNER:-nfernandezsanz}}"
GITHUB_REPOSITORY_NAME="${GITHUB_REPOSITORY_NAME:-retOS}"
GITHUB_REPOSITORY_FULL="${GITHUB_REPOSITORY:-${REPOSITORY_OWNER}/${GITHUB_REPOSITORY_NAME}}"
BACKEND_IMAGE="${BACKEND_IMAGE:-${REGISTRY}/${REPOSITORY_OWNER}/retos-backend}"
WEB_IMAGE="${WEB_IMAGE:-${REGISTRY}/${REPOSITORY_OWNER}/retos-web}"
BACKEND_DIGEST="${BACKEND_DIGEST:-}"
WEB_DIGEST="${WEB_DIGEST:-}"
CERTIFICATE_IDENTITY_REGEXP="${CERTIFICATE_IDENTITY_REGEXP:-https://github.com/${GITHUB_REPOSITORY_FULL}/.github/workflows/release.yml@refs/.*}"
CERTIFICATE_OIDC_ISSUER="${CERTIFICATE_OIDC_ISSUER:-https://token.actions.githubusercontent.com}"
DRY_RUN="${RETOS_RELEASE_EVIDENCE_DRY_RUN:-0}"
SKIP_TAG_DIGEST_CHECK="${RETOS_SKIP_TAG_DIGEST_CHECK:-0}"

require_value VERSION "${VERSION}"
require_value BACKEND_DIGEST "${BACKEND_DIGEST}"
require_value WEB_DIGEST "${WEB_DIGEST}"
require_value BACKEND_IMAGE "${BACKEND_IMAGE}"
require_value WEB_IMAGE "${WEB_IMAGE}"
validate_version "${VERSION}"
validate_digest BACKEND_DIGEST "${BACKEND_DIGEST}"
validate_digest WEB_DIGEST "${WEB_DIGEST}"

for image in "${BACKEND_IMAGE}" "${WEB_IMAGE}"; do
  [[ "${image}" == "${REGISTRY}/"* ]] || fail "${image} must use ${REGISTRY}"
  [[ "${image}" != *":latest" ]] || fail "${image} must not use latest"
done

verify_tag_digest() {
  local image="$1"
  local digest="$2"
  local tag_ref="${image}:${VERSION}"

  if [[ "${DRY_RUN}" == "1" ]]; then
    printf 'DRY RUN: docker buildx imagetools inspect --format %q %q\n' '{{.Manifest.Digest}}' "${tag_ref}"
    return
  fi

  if [[ "${SKIP_TAG_DIGEST_CHECK}" == "1" ]]; then
    printf 'SKIPPED: tag digest check for %s\n' "${tag_ref}"
    return
  fi

  command -v docker >/dev/null 2>&1 || fail "docker is required for tag digest verification unless RETOS_SKIP_TAG_DIGEST_CHECK=1"
  local resolved_digest
  resolved_digest="$(docker buildx imagetools inspect --format '{{.Manifest.Digest}}' "${tag_ref}")"
  [[ -n "${resolved_digest}" ]] || fail "could not resolve digest for ${tag_ref}"
  [[ "${resolved_digest}" == "${digest}" ]] || fail "${tag_ref} resolves to ${resolved_digest}, expected ${digest}"
}

verify_image() {
  local image="$1"
  local digest="$2"
  local ref="${image}@${digest}"

  if [[ "${DRY_RUN}" == "1" ]]; then
    printf 'DRY RUN: cosign verify --certificate-identity-regexp %q --certificate-oidc-issuer %q %q\n' \
      "${CERTIFICATE_IDENTITY_REGEXP}" "${CERTIFICATE_OIDC_ISSUER}" "${ref}"
    return
  fi

  command -v cosign >/dev/null 2>&1 || fail "cosign is required unless RETOS_RELEASE_EVIDENCE_DRY_RUN=1"
  cosign verify \
    --certificate-identity-regexp "${CERTIFICATE_IDENTITY_REGEXP}" \
    --certificate-oidc-issuer "${CERTIFICATE_OIDC_ISSUER}" \
    "${ref}"
}

verify_image "${BACKEND_IMAGE}" "${BACKEND_DIGEST}"
verify_image "${WEB_IMAGE}" "${WEB_DIGEST}"
verify_tag_digest "${BACKEND_IMAGE}" "${BACKEND_DIGEST}"
verify_tag_digest "${WEB_IMAGE}" "${WEB_DIGEST}"

cat <<EOF
Published release evidence OK:
- Version: ${VERSION}
- Backend: ${BACKEND_IMAGE}:${VERSION} @ ${BACKEND_DIGEST}
- Web: ${WEB_IMAGE}:${VERSION} @ ${WEB_DIGEST}
- Immutable tags resolve to the recorded digests
- Certificate identity: ${CERTIFICATE_IDENTITY_REGEXP}
- OIDC issuer: ${CERTIFICATE_OIDC_ISSUER}
EOF
