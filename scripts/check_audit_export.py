#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def canonical_json_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def parse_occurred_at(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def audit_event_hash(entry: dict[str, Any]) -> str:
    occurred_at = parse_occurred_at(str(entry["occurred_at"]))
    return canonical_json_hash(
        {
            "event_id": entry["event_id"],
            "trace_id": entry.get("trace_id"),
            "event_stream": entry["event_stream"],
            "event_type": entry["event_type"],
            "occurred_at": occurred_at.isoformat(),
            "payload_hash": entry["payload_hash"],
            "prev_hash": entry.get("prev_hash"),
        }
    )


def export_events_by_id(export: dict[str, Any]) -> dict[str, dict[str, Any]]:
    events: dict[str, dict[str, Any]] = {}
    for event in export.get("journal_events", []):
        events[str(event["id"])] = event
    for event in export.get("progress_events", []):
        events[str(event["id"])] = event
    return events


def integrity_failures(export: dict[str, Any]) -> list[dict[str, str | None]]:
    integrity = export.get("integrity") or {}
    chain = integrity.get("chain") or []
    events_by_id = export_events_by_id(export)
    failures: list[dict[str, str | None]] = []
    for entry in chain:
        event_id = str(entry.get("event_id"))
        event = events_by_id.get(event_id)
        if event is None:
            failures.append(
                {
                    "event_id": event_id,
                    "event_stream": str(entry.get("event_stream")),
                    "event_type": str(entry.get("event_type")),
                    "reason": "event_missing_from_export",
                    "expected": "journal_events or progress_events entry",
                    "actual": None,
                }
            )
            continue
        actual_payload_hash = canonical_json_hash(event.get("payload") or {})
        if entry.get("payload_hash") != actual_payload_hash:
            failures.append(
                {
                    "event_id": event_id,
                    "event_stream": str(entry.get("event_stream")),
                    "event_type": str(entry.get("event_type")),
                    "reason": "payload_hash_mismatch",
                    "expected": actual_payload_hash,
                    "actual": str(entry.get("payload_hash")),
                }
            )
        expected_hash = audit_event_hash(entry)
        if entry.get("event_hash") != expected_hash:
            failures.append(
                {
                    "event_id": event_id,
                    "event_stream": str(entry.get("event_stream")),
                    "event_type": str(entry.get("event_type")),
                    "reason": "event_hash_mismatch",
                    "expected": expected_hash,
                    "actual": str(entry.get("event_hash")),
                }
            )
    return failures


def continuity_gaps(export: dict[str, Any]) -> list[dict[str, str | None]]:
    chain = (export.get("integrity") or {}).get("chain") or []
    gaps: list[dict[str, str | None]] = []
    previous_hash: str | None = None
    for index, entry in enumerate(chain):
        if index > 0 and entry.get("prev_hash") != previous_hash:
            gaps.append(
                {
                    "event_id": str(entry.get("event_id")),
                    "event_stream": str(entry.get("event_stream")),
                    "event_type": str(entry.get("event_type")),
                    "reason": "prev_hash_gap",
                    "expected": previous_hash,
                    "actual": str(entry.get("prev_hash")),
                }
            )
        previous_hash = str(entry.get("event_hash"))
    return gaps


def validate_export(export: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if export.get("schema_version") != "retos.audit-export.v2":
        errors.append("schema_version must be retos.audit-export.v2")
    integrity = export.get("integrity")
    if not isinstance(integrity, dict):
        return [*errors, "integrity block is required"]
    chain = integrity.get("chain")
    if not isinstance(chain, list):
        return [*errors, "integrity.chain must be a list"]
    expected_count = len(export.get("journal_events", [])) + len(
        export.get("progress_events", [])
    )
    if integrity.get("event_count") != expected_count:
        errors.append(
            "integrity.event_count "
            f"{integrity.get('event_count')} does not match exported events {expected_count}"
        )
    expected_head = chain[-1]["event_hash"] if chain else None
    if integrity.get("head_hash") != expected_head:
        errors.append("integrity.head_hash does not match the last chain event")
    failures = integrity_failures(export)
    reported_failures = integrity.get("failures") or []
    if bool(failures) == bool(integrity.get("valid")):
        errors.append("integrity.valid does not match recalculated failures")
    reported_reasons = {
        (failure.get("event_id"), failure.get("reason"))
        for failure in reported_failures
    }
    recalculated_reasons = {
        (failure.get("event_id"), failure.get("reason")) for failure in failures
    }
    if reported_reasons != recalculated_reasons:
        errors.append("integrity.failures does not match recalculated failure reasons")
    reported_gap_reasons = {
        (gap.get("event_id"), gap.get("reason"))
        for gap in integrity.get("continuity_gaps", [])
    }
    recalculated_gap_reasons = {
        (gap.get("event_id"), gap.get("reason")) for gap in continuity_gaps(export)
    }
    if reported_gap_reasons != recalculated_gap_reasons:
        errors.append(
            "integrity.continuity_gaps does not match recalculated gap reasons"
        )
    return errors


def self_test_export() -> dict[str, Any]:
    occurred_at = "2026-06-29T12:00:00+00:00"
    payload = {"kind": "index.domain", "status": "queued"}
    payload_hash = canonical_json_hash(payload)
    entry = {
        "event_id": "event-1",
        "trace_id": "job-1",
        "event_stream": "journal",
        "event_type": "job.created",
        "occurred_at": occurred_at,
        "payload_hash": payload_hash,
        "prev_hash": None,
    }
    event_hash = audit_event_hash(entry)
    entry["event_hash"] = event_hash
    return {
        "schema_version": "retos.audit-export.v2",
        "generated_at": "2026-06-29T12:00:01+00:00",
        "limit": 200,
        "journal_events": [
            {
                "id": "event-1",
                "trace_id": "job-1",
                "payload_hash": payload_hash,
                "prev_hash": None,
                "event_hash": event_hash,
                "occurred_at": occurred_at,
                "actor": "admin@retos.dev",
                "event_type": "job.created",
                "entity_type": "job",
                "entity_id": "job-1",
                "payload": payload,
            }
        ],
        "progress_events": [],
        "integrity": {
            "algorithm": "sha256",
            "canonicalization": "json-sort-keys-v1",
            "valid": True,
            "event_count": 1,
            "head_hash": event_hash,
            "failures": [],
            "continuity_gaps": [],
            "chain": [entry],
        },
    }


def run(export_path: Path | None, *, self_test: bool) -> int:
    if self_test:
        export = self_test_export()
    else:
        if export_path is None:
            raise ValueError("export_path is required unless self_test is enabled")
        export = json.loads(export_path.read_text(encoding="utf-8"))
    errors = validate_export(export)
    if errors:
        for error in errors:
            print(f"Audit export failed: {error}")
        return 1
    source = "self-test" if self_test else str(export_path)
    integrity = export["integrity"]
    print(
        "Audit export OK: "
        f"{source}, {integrity['event_count']} events, "
        f"head={integrity['head_hash'] or 'none'}, valid={integrity['valid']}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a RetOS /audit/export JSON file."
    )
    parser.add_argument("--export", type=Path, help="Path to retos-audit-export.json")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run the verifier against a built-in valid export fixture.",
    )
    args = parser.parse_args()
    if not args.self_test and args.export is None:
        parser.error("--export is required unless --self-test is used")
    return run(args.export, self_test=args.self_test)


if __name__ == "__main__":
    raise SystemExit(main())
