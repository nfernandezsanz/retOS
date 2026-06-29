"""Add soft archive state to domains."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_domain_archive"
down_revision: str | None = "0008_audit_hash_chain_columns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("domains", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_domains_archived_at"), "domains", ["archived_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_domains_archived_at"), table_name="domains")
    op.drop_column("domains", "archived_at")
