"""add extended_attributes and configs table

Revision ID: 15f6e8597117
Revises: 65b9bcf5df2a
Create Date: 2026-08-31 17:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "15f6e8597117"
down_revision: str | None = "65b9bcf5df2a"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("extended_attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "patient_profiles",
        sa.Column("extended_attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "professional_profiles",
        sa.Column("extended_attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "bookings",
        sa.Column("extended_attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    op.create_table(
        "configs",
        sa.Column("key", sa.String(length=150), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_configs")),
    )
    op.create_index(op.f("ix_configs_key"), "configs", ["key"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_configs_key"), table_name="configs")
    op.drop_table("configs")

    op.drop_column("bookings", "extended_attributes")
    op.drop_column("professional_profiles", "extended_attributes")
    op.drop_column("patient_profiles", "extended_attributes")
    op.drop_column("users", "extended_attributes")
