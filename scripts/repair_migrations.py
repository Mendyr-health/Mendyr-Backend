"""Detect and repair a stale/missing `alembic_version` row against the live schema.

Symptom this fixes: `alembic upgrade head` fails with "type/relation ... already exists"
because the database's actual schema is ahead of what `alembic_version` records (or that
table is missing/empty entirely) — e.g. the schema was created outside Alembic once, or the
tracking table got reset independently of the real tables. This never happens from normal
`alembic upgrade head` usage; it needs some other write path to have touched the DB.

Usage:
    uv run python -m scripts.repair_migrations            # dry run (default) — reports only
    uv run python -m scripts.repair_migrations --apply     # actually stamps alembic_version

This only ever writes to Alembic's own bookkeeping table (`alembic_version`) — it never runs
migration DDL and never touches any other table's data or schema.

Add a new (revision_id, label, marker) entry here whenever you add a migration whose presence
you want this script able to detect — pick something that only exists once that migration has
run (a table or column it introduces).
"""
import argparse
from collections.abc import Callable

import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.engine import Inspector

from alembic import command
from app.core.config import settings

# Ordered oldest -> newest.
MIGRATION_MARKERS: list[tuple[str, str, Callable[[Inspector], bool]]] = [
    ("fd5a5a27db20", "initial schema", lambda insp: insp.has_table("coupons")),
    (
        "65b9bcf5df2a",
        "add ci_migration_test_note column",
        lambda insp: any(
            c["name"] == "ci_migration_test_note" for c in insp.get_columns("service_categories")
        ),
    ),
    (
        "15f6e8597117",
        "add extended_attributes and configs table",
        lambda insp: insp.has_table("configs"),
    ),
]


def detect_actual_revision(insp: Inspector) -> str | None:
    """Walk newest -> oldest, return the first (highest) revision whose marker matches."""
    for revision, _label, marker in reversed(MIGRATION_MARKERS):
        if marker(insp):
            return revision
    return None


def get_stamped_revision(conn: sa.Connection) -> str | None:
    if not sa.inspect(conn).has_table("alembic_version"):
        return None
    row = conn.execute(sa.text("SELECT version_num FROM alembic_version")).fetchone()
    return row[0] if row else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually stamp alembic_version (default: dry run, report only).",
    )
    args = parser.parse_args()

    engine = create_engine(settings.SQLALCHEMY_SYNC_DATABASE_URI)
    with engine.connect() as conn:
        stamped = get_stamped_revision(conn)
        detected = detect_actual_revision(sa.inspect(conn))

    print(f"alembic_version currently records: {stamped or '(none)'}")
    print(f"Schema inspection detects revision: {detected or '(none — looks like a fresh DB)'}")

    if stamped is not None:
        print("alembic_version already has a value — nothing to repair.")
        return
    if detected is None:
        print(
            "No known migration markers found — this looks like a genuinely fresh database. "
            "`alembic upgrade head` will run normally. Nothing to repair."
        )
        return

    print(f"\nDrift detected: schema matches revision {detected!r} but alembic_version is empty.")
    if not args.apply:
        print(f"Dry run only — re-run with --apply to stamp the DB at {detected!r}.")
        return

    command.stamp(Config("alembic.ini"), detected)
    print(f"Stamped alembic_version = {detected!r}. Safe to run `alembic upgrade head` now.")


if __name__ == "__main__":
    main()
