"""Custom SQLAlchemy column types shared across models."""

from enum import Enum as PyEnum
from typing import TypeVar

import sqlalchemy as sa

E = TypeVar("E", bound=PyEnum)


def pg_enum(enum_cls: type[E], name: str) -> sa.Enum:
    """Native Postgres ENUM whose DB labels are the StrEnum's `.value` (lowercase), not the
    Python member `.name` (SQLAlchemy's default). Without `values_callable`, a column typed
    `Enum(UserRole)` would store 'PATIENT' in Postgres instead of 'patient' — surprising for
    anyone querying the database directly and inconsistent with `app.core.constants`, where the
    string value *is* the canonical wire/DB representation.
    """
    return sa.Enum(
        enum_cls, name=name, native_enum=True, values_callable=lambda obj: [e.value for e in obj]
    )
