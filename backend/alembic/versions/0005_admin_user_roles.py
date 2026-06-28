"""Persist admin user roles."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_admin_user_roles"
down_revision: str | None = "0004_document_archive"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "admin_users",
        sa.Column("roles", sa.JSON(), nullable=True),
    )
    op.execute("UPDATE admin_users SET roles = '[\"admin\"]' WHERE roles IS NULL")
    with op.batch_alter_table("admin_users") as batch_op:
        batch_op.alter_column("roles", existing_type=sa.JSON(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("admin_users") as batch_op:
        batch_op.drop_column("roles")
