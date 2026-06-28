#!/usr/bin/env bash
set -euo pipefail

require_built_images="${RETOS_REQUIRE_BUILT_IMAGES:-0}"
image_tag="${RETOS_IMAGE_TAG:-local}"

python3 - <<'PY'
from __future__ import annotations

from pathlib import Path

required_labels = (
    "org.opencontainers.image.title",
    "org.opencontainers.image.description",
    "org.opencontainers.image.source",
    "org.opencontainers.image.url",
    "org.opencontainers.image.documentation",
    "org.opencontainers.image.licenses",
    "org.opencontainers.image.version",
    "org.opencontainers.image.revision",
    "org.opencontainers.image.created",
)

dockerfiles = {
    "backend/Dockerfile": "RetOS Backend",
    "frontend/Dockerfile": "RetOS Web",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"Image metadata failed: {message}")


for dockerfile, title in dockerfiles.items():
    content = Path(dockerfile).read_text(encoding="utf-8")
    require("LABEL " in content, f"{dockerfile} must define OCI labels")
    for label in required_labels:
        require(label in content, f"{dockerfile} missing {label}")
    require(
        f'org.opencontainers.image.title="{title}"' in content,
        f"{dockerfile} has wrong title label",
    )
    require(
        'org.opencontainers.image.licenses="MIT"' in content,
        f"{dockerfile} must declare MIT license",
    )
    require(
        'org.opencontainers.image.source="https://github.com/nfernandezsanz/retOS"'
        in content,
        f"{dockerfile} must point labels at the public repository",
    )

print("Image metadata source OK: backend and web Dockerfiles define required OCI labels.")
PY

if [[ "${require_built_images}" != "1" ]]; then
  exit 0
fi

required_labels=(
  "org.opencontainers.image.title"
  "org.opencontainers.image.description"
  "org.opencontainers.image.source"
  "org.opencontainers.image.url"
  "org.opencontainers.image.documentation"
  "org.opencontainers.image.licenses"
  "org.opencontainers.image.version"
  "org.opencontainers.image.revision"
  "org.opencontainers.image.created"
)

for image in "retos-backend:${image_tag}" "retos-web:${image_tag}"; do
  for label in "${required_labels[@]}"; do
    value="$(docker image inspect --format "{{ index .Config.Labels \"${label}\" }}" "${image}")"
    if [[ -z "${value}" || "${value}" == "<no value>" ]]; then
      echo "Image metadata failed: ${image} missing ${label}" >&2
      exit 1
    fi
  done
done

echo "Image metadata inspect OK: retos-backend:${image_tag} and retos-web:${image_tag} include required OCI labels."
