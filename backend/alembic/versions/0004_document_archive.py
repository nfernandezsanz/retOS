"""Add soft archive timestamp to documents."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_document_archive"
down_revision: str | None = "0003_widen_artifact_hash"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(op.f("ix_documents_archived_at"), "documents", ["archived_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_documents_archived_at"), table_name="documents")
    op.drop_column("documents", "archived_at")
