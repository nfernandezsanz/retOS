"""Add trace identifiers to audit event tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_audit_trace_ids"
down_revision: str | None = "0006_admin_user_domain_grants"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("journal_events", sa.Column("trace_id", sa.String(length=80), nullable=True))
    op.add_column("progress_events", sa.Column("trace_id", sa.String(length=80), nullable=True))
    op.create_index(op.f("ix_journal_events_trace_id"), "journal_events", ["trace_id"])
    op.create_index(op.f("ix_progress_events_trace_id"), "progress_events", ["trace_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_progress_events_trace_id"), table_name="progress_events")
    op.drop_index(op.f("ix_journal_events_trace_id"), table_name="journal_events")
    op.drop_column("progress_events", "trace_id")
    op.drop_column("journal_events", "trace_id")
