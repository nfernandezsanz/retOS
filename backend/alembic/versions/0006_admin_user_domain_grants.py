"""Add domain grants for local accounts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_admin_user_domain_grants"
down_revision: str | None = "0005_admin_user_roles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admin_user_domain_grants",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("admin_user_id", sa.String(length=36), nullable=False),
        sa.Column("domain_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["admin_user_id"], ["admin_users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["domain_id"], ["domains.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "admin_user_id",
            "domain_id",
            name="uq_admin_user_domain_grants_user_domain",
        ),
    )
    op.create_index(
        op.f("ix_admin_user_domain_grants_admin_user_id"),
        "admin_user_domain_grants",
        ["admin_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_admin_user_domain_grants_domain_id"),
        "admin_user_domain_grants",
        ["domain_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_admin_user_domain_grants_domain_id"),
        table_name="admin_user_domain_grants",
    )
    op.drop_index(
        op.f("ix_admin_user_domain_grants_admin_user_id"),
        table_name="admin_user_domain_grants",
    )
    op.drop_table("admin_user_domain_grants")
