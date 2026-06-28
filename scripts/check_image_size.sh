#!/usr/bin/env bash
set -euo pipefail

require_built_images="${RETOS_REQUIRE_BUILT_IMAGES:-0}"
image_tag="${RETOS_IMAGE_TAG:-local}"
backend_limit_bytes="${RETOS_BACKEND_IMAGE_MAX_BYTES:-1400000000}"
web_limit_bytes="${RETOS_WEB_IMAGE_MAX_BYTES:-200000000}"
export RETOS_BACKEND_IMAGE_MAX_BYTES="${backend_limit_bytes}"
export RETOS_WEB_IMAGE_MAX_BYTES="${web_limit_bytes}"

python3 - <<'PY'
from __future__ import annotations

import os
from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"Image size failed: {message}")


def positive_int(name: str) -> int:
    value = os.environ.get(name, "")
    require(value.isdigit(), f"{name} must be a positive integer byte limit")
    parsed = int(value)
    require(parsed > 0, f"{name} must be greater than zero")
    return parsed


backend_limit = positive_int("RETOS_BACKEND_IMAGE_MAX_BYTES")
web_limit = positive_int("RETOS_WEB_IMAGE_MAX_BYTES")
require(
    backend_limit >= 1_000_000_000,
    "backend budget should leave room for Python, OCR, and PDF runtime dependencies",
)
require(
    web_limit >= 50_000_000,
    "web budget should leave room for the Nginx runtime and bundled assets",
)

docker_docs = Path("docs/docker.md").read_text(encoding="utf-8")
release_docs = Path("docs/release-process.md").read_text(encoding="utf-8")

for phrase in (
    "RETOS_BACKEND_IMAGE_MAX_BYTES",
    "RETOS_WEB_IMAGE_MAX_BYTES",
    "scripts/check_image_size.sh",
):
    require(phrase in docker_docs, f"docs/docker.md missing {phrase}")
    require(phrase in release_docs, f"docs/release-process.md missing {phrase}")

print("Image size source OK: budgets and release documentation are aligned.")
PY

if [[ "${require_built_images}" != "1" ]]; then
  exit 0
fi

format_bytes() {
  python3 - "$1" <<'PY'
from __future__ import annotations

import sys

size = int(sys.argv[1])
units = ("B", "KB", "MB", "GB")
value = float(size)
for unit in units:
    if value < 1024 or unit == units[-1]:
        print(f"{value:.1f}{unit}")
        break
    value /= 1024
PY
}

check_image() {
  local image="$1"
  local limit="$2"
  local size
  size="$(docker image inspect --format '{{ .Size }}' "${image}")"
  if (( size > limit )); then
    echo "Image size failed: ${image} is $(format_bytes "${size}") and exceeds $(format_bytes "${limit}")" >&2
    exit 1
  fi
  echo "Image size OK: ${image} is $(format_bytes "${size}") within $(format_bytes "${limit}")."
}

check_image "retos-backend:${image_tag}" "${backend_limit_bytes}"
check_image "retos-web:${image_tag}" "${web_limit_bytes}"
