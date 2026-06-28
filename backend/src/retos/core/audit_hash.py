import hashlib
import json
from datetime import UTC, datetime
from typing import Any

AUDIT_HASH_ALGORITHM = "sha256"
AUDIT_HASH_CANONICALIZATION = "json-sort-keys-v1"


def canonical_json_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def audit_payload_hash(payload: dict[str, Any]) -> str:
    return canonical_json_hash(payload)


def audit_event_hash(
    *,
    event_id: str,
    trace_id: str | None,
    event_stream: str,
    event_type: str,
    occurred_at: datetime,
    payload_hash: str,
    prev_hash: str | None,
) -> str:
    canonical_occurred_at = occurred_at
    if canonical_occurred_at.tzinfo is None:
        canonical_occurred_at = canonical_occurred_at.replace(tzinfo=UTC)
    else:
        canonical_occurred_at = canonical_occurred_at.astimezone(UTC)
    return canonical_json_hash(
        {
            "event_id": event_id,
            "trace_id": trace_id,
            "event_stream": event_stream,
            "event_type": event_type,
            "occurred_at": canonical_occurred_at.isoformat(),
            "payload_hash": payload_hash,
            "prev_hash": prev_hash,
        }
    )
