from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

JobKind = Literal["ingest.source", "index.domain", "eval.run", "agent.query"]
JobStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]


@dataclass(frozen=True)
class Job:
    id: str
    kind: JobKind
    status: JobStatus
    domain_id: str | None
    source_id: str | None
    payload: dict[str, Any]
    error: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class JournalEvent:
    id: str
    trace_id: str | None
    payload_hash: str | None
    prev_hash: str | None
    event_hash: str | None
    occurred_at: datetime
    actor: str
    event_type: str
    entity_type: str
    entity_id: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class ProgressEvent:
    id: str
    trace_id: str | None
    payload_hash: str | None
    prev_hash: str | None
    event_hash: str | None
    job_id: str | None
    occurred_at: datetime
    event_type: str
    message: str
    payload: dict[str, Any]
