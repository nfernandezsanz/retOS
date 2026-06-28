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

require_value VERSION "${VERSION}"
require_value BACKEND_DIGEST "${BACKEND_DIGEST}"
require_value WEB_DIGEST "${WEB_DIGEST}"
require_value BACKEND_IMAGE "${BACKEND_IMAGE}"
require_value WEB_IMAGE "${WEB_IMAGE}"
validate_digest BACKEND_DIGEST "${BACKEND_DIGEST}"
validate_digest WEB_DIGEST "${WEB_DIGEST}"

if [[ "${VERSION}" == "local" || "${VERSION}" == "latest" ]]; then
  fail "VERSION must be immutable, not ${VERSION}"
fi

for image in "${BACKEND_IMAGE}" "${WEB_IMAGE}"; do
  [[ "${image}" == "${REGISTRY}/"* ]] || fail "${image} must use ${REGISTRY}"
  [[ "${image}" != *":latest" ]] || fail "${image} must not use latest"
done

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

cat <<EOF
Published release evidence OK:
- Version: ${VERSION}
- Backend: ${BACKEND_IMAGE}:${VERSION} @ ${BACKEND_DIGEST}
- Web: ${WEB_IMAGE}:${VERSION} @ ${WEB_DIGEST}
- Certificate identity: ${CERTIFICATE_IDENTITY_REGEXP}
- OIDC issuer: ${CERTIFICATE_OIDC_ISSUER}
EOF
