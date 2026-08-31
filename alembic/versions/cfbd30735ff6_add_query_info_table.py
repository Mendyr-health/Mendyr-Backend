"""add query_info table

Revision ID: cfbd30735ff6
Revises: 268cb9f2b343
Create Date: 2026-08-31 19:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "cfbd30735ff6"
down_revision: str | None = "268cb9f2b343"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "query_info",
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("batch_size", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_query_info")),
    )
    op.create_index(op.f("ix_query_info_name"), "query_info", ["name"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_query_info_name"), table_name="query_info")
    op.drop_table("query_info")
