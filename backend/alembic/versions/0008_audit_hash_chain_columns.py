"""Persist audit hash-chain columns."""

from collections.abc import Sequence
from datetime import UTC, datetime
import hashlib
import json
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0008_audit_hash_chain_columns"
down_revision: str | None = "0007_audit_trace_ids"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def canonical_json_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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


def upgrade() -> None:
    op.add_column(
        "journal_events",
        sa.Column("payload_hash", sa.String(length=64), nullable=True),
    )
    op.add_column("journal_events", sa.Column("prev_hash", sa.String(length=64), nullable=True))
    op.add_column("journal_events", sa.Column("event_hash", sa.String(length=64), nullable=True))
    op.add_column(
        "progress_events",
        sa.Column("payload_hash", sa.String(length=64), nullable=True),
    )
    op.add_column("progress_events", sa.Column("prev_hash", sa.String(length=64), nullable=True))
    op.add_column("progress_events", sa.Column("event_hash", sa.String(length=64), nullable=True))
    op.create_index(op.f("ix_journal_events_event_hash"), "journal_events", ["event_hash"])
    op.create_index(op.f("ix_progress_events_event_hash"), "progress_events", ["event_hash"])

    bind = op.get_bind()
    metadata = sa.MetaData()
    journal_events = sa.Table(
        "journal_events",
        metadata,
        sa.Column("id", sa.String(length=36)),
        sa.Column("trace_id", sa.String(length=80)),
        sa.Column("occurred_at", sa.DateTime(timezone=True)),
        sa.Column("event_type", sa.String(length=120)),
        sa.Column("payload", sa.JSON()),
        sa.Column("payload_hash", sa.String(length=64)),
        sa.Column("prev_hash", sa.String(length=64)),
        sa.Column("event_hash", sa.String(length=64)),
    )
    progress_events = sa.Table(
        "progress_events",
        metadata,
        sa.Column("id", sa.String(length=36)),
        sa.Column("trace_id", sa.String(length=80)),
        sa.Column("occurred_at", sa.DateTime(timezone=True)),
        sa.Column("event_type", sa.String(length=120)),
        sa.Column("payload", sa.JSON()),
        sa.Column("payload_hash", sa.String(length=64)),
        sa.Column("prev_hash", sa.String(length=64)),
        sa.Column("event_hash", sa.String(length=64)),
    )
    rows = [
        ("journal", row)
        for row in bind.execute(
            sa.select(
                journal_events.c.id,
                journal_events.c.trace_id,
                journal_events.c.occurred_at,
                journal_events.c.event_type,
                journal_events.c.payload,
            )
        )
    ] + [
        ("progress", row)
        for row in bind.execute(
            sa.select(
                progress_events.c.id,
                progress_events.c.trace_id,
                progress_events.c.occurred_at,
                progress_events.c.event_type,
                progress_events.c.payload,
            )
        )
    ]
    prev_hash: str | None = None
    for event_stream, row in sorted(
        rows,
        key=lambda item: (item[1].occurred_at, item[0], item[1].id),
    ):
        payload = row.payload or {}
        payload_hash = canonical_json_hash(payload)
        event_hash = audit_event_hash(
            event_id=row.id,
            trace_id=row.trace_id,
            event_stream=event_stream,
            event_type=row.event_type,
            occurred_at=row.occurred_at,
            payload_hash=payload_hash,
            prev_hash=prev_hash,
        )
        table = journal_events if event_stream == "journal" else progress_events
        bind.execute(
            table.update()
            .where(table.c.id == row.id)
            .values(
                payload_hash=payload_hash,
                prev_hash=prev_hash,
                event_hash=event_hash,
            )
        )
        prev_hash = event_hash


def downgrade() -> None:
    op.drop_index(op.f("ix_progress_events_event_hash"), table_name="progress_events")
    op.drop_index(op.f("ix_journal_events_event_hash"), table_name="journal_events")
    op.drop_column("progress_events", "event_hash")
    op.drop_column("progress_events", "prev_hash")
    op.drop_column("progress_events", "payload_hash")
    op.drop_column("journal_events", "event_hash")
    op.drop_column("journal_events", "prev_hash")
    op.drop_column("journal_events", "payload_hash")
