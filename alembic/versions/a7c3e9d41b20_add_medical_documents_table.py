"""add medical_documents table; make sure user_role has super_admin

Revision ID: a7c3e9d41b20
Revises: cfbd30735ff6
Create Date: 2026-11-02 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c3e9d41b20"
down_revision: str | None = "cfbd30735ff6"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # `super_admin` was added to some databases by hand, never by a migration. IF NOT EXISTS
    # makes this a no-op there; ADD VALUE can't run inside a transaction block on older
    # Postgres, hence the autocommit block.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'super_admin'")

    op.create_table(
        "medical_documents",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("booking_id", sa.UUID(), nullable=True),
        sa.Column("document_type", sa.String(length=30), nullable=False),
        sa.Column("title", sa.String(length=150), nullable=True),
        sa.Column("file_key", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_medical_documents_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["booking_id"],
            ["bookings.id"],
            name=op.f("fk_medical_documents_booking_id_bookings"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_medical_documents")),
    )
    op.create_index("ix_medical_documents_user_id", "medical_documents", ["user_id"])
    op.create_index("ix_medical_documents_booking_id", "medical_documents", ["booking_id"])


def downgrade() -> None:
    op.drop_index("ix_medical_documents_booking_id", table_name="medical_documents")
    op.drop_index("ix_medical_documents_user_id", table_name="medical_documents")
    op.drop_table("medical_documents")
    # Postgres can't drop an enum value; super_admin stays.
