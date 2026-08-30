"""Email + password auth: phone_number becomes optional

Email is now the login credential, so a user can register without ever giving a phone
number. `email` / `hashed_password` are left DB-nullable on purpose: pre-existing
OTP-era rows have neither, and the app layer requires both for every new account.

Revision ID: a1c4e7b90f21
Revises: 65b9bcf5df2a
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1c4e7b90f21"
down_revision: str | None = "65b9bcf5df2a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "users", "phone_number", existing_type=sa.String(length=15), nullable=True
    )


def downgrade() -> None:
    # Rows registered by email with no phone number can't satisfy a NOT NULL constraint;
    # they'd have to be backfilled or deleted before this downgrade can run.
    op.alter_column(
        "users", "phone_number", existing_type=sa.String(length=15), nullable=False
    )
