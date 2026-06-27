"""Widen artifact hash storage."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_widen_artifact_hash"
down_revision: str | None = "0002_admin_users"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("artifacts") as batch_op:
        batch_op.alter_column(
            "sha256",
            existing_type=sa.String(length=64),
            type_=sa.String(length=135),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("artifacts") as batch_op:
        batch_op.alter_column(
            "sha256",
            existing_type=sa.String(length=135),
            type_=sa.String(length=64),
            existing_nullable=False,
        )
