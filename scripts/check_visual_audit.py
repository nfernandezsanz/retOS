#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "frontend" / "visual-audit" / "manifest.json"
EXPECTED_SCREENSHOTS = {
    "desktop": {
        "path": "visual-audit/retos-console-desktop.png",
        "viewport": {"width": 1440, "height": 900},
    },
    "mobile": {
        "path": "visual-audit/retos-console-mobile.png",
        "viewport": {"width": 390, "height": 844},
    },
}


class VisualAuditError(RuntimeError):
    pass


@dataclass(frozen=True)
class VisualAuditResult:
    screenshots: int
    total_size_bytes: int


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise VisualAuditError(f"manifest is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise VisualAuditError("manifest must be a JSON object")
    return payload


def validate_visual_audit(manifest_path: Path = DEFAULT_MANIFEST) -> VisualAuditResult:
    if not manifest_path.is_file():
        raise VisualAuditError(f"visual audit manifest not found: {manifest_path}")
    manifest = load_json(manifest_path)
    if manifest.get("generated_by") != "frontend/e2e/app.spec.ts":
        raise VisualAuditError(
            "manifest generated_by must remain frontend/e2e/app.spec.ts"
        )
    screenshots = manifest.get("screenshots")
    if not isinstance(screenshots, list):
        raise VisualAuditError("manifest screenshots must be a list")
    by_name = {
        record.get("name"): record
        for record in screenshots
        if isinstance(record, dict) and record.get("name")
    }
    missing = sorted(set(EXPECTED_SCREENSHOTS) - set(by_name))
    if missing:
        raise VisualAuditError("missing screenshot record(s): " + ", ".join(missing))

    total_size = 0
    for name, expected in EXPECTED_SCREENSHOTS.items():
        record = by_name[name]
        validate_record(
            name=name,
            record=record,
            expected_path=str(expected["path"]),
            expected_viewport=dict(expected["viewport"]),
            manifest_path=manifest_path,
        )
        total_size += int(record["size_bytes"])
    return VisualAuditResult(
        screenshots=len(EXPECTED_SCREENSHOTS),
        total_size_bytes=total_size,
    )


def validate_record(
    *,
    name: str,
    record: dict[str, Any],
    expected_path: str,
    expected_viewport: dict[str, int],
    manifest_path: Path,
) -> None:
    if record.get("path") != expected_path:
        raise VisualAuditError(f"{name} screenshot path must be {expected_path}")
    viewport = record.get("viewport")
    if viewport != expected_viewport:
        raise VisualAuditError(f"{name} viewport must be {expected_viewport}")
    expected_sha = record.get("sha256")
    if not isinstance(expected_sha, str) or len(expected_sha) != 64:
        raise VisualAuditError(f"{name} screenshot must record a sha256 digest")
    expected_size = record.get("size_bytes")
    if not isinstance(expected_size, int) or expected_size <= 0:
        raise VisualAuditError(f"{name} screenshot must record positive size_bytes")

    image_path = manifest_path.parent.parent / expected_path
    if not image_path.is_file():
        raise VisualAuditError(f"{name} screenshot file not found: {image_path}")
    actual_size = image_path.stat().st_size
    if actual_size != expected_size:
        raise VisualAuditError(
            f"{name} screenshot size changed: manifest={expected_size}, actual={actual_size}"
        )
    actual_sha = sha256(image_path)
    if actual_sha != expected_sha:
        raise VisualAuditError(
            f"{name} screenshot sha256 changed: manifest={expected_sha}, actual={actual_sha}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate local RetOS frontend visual-audit evidence."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="Path to frontend/visual-audit/manifest.json.",
    )
    args = parser.parse_args()
    try:
        result = validate_visual_audit(args.manifest)
    except VisualAuditError as exc:
        print(f"Visual audit failed: {exc}", file=sys.stderr)
        return 1
    print(
        "Visual audit OK: "
        f"{result.screenshots} screenshot(s), {result.total_size_bytes} bytes, "
        "manifest hashes verified."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
