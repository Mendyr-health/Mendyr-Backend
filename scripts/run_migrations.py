#!/usr/bin/env python3
"""Plain-SQL migration runner — replaces Alembic.

Applies every *.sql file in migrations/ (repo root) that hasn't already been applied, in
filename order, each inside its own transaction. Applied filenames are tracked in a
`schema_migrations` table so re-running this script is a no-op once everything is applied.

Usage:
    uv run python scripts/run_migrations.py            # apply all pending migrations
    uv run python scripts/run_migrations.py --dry-run   # print what would run, don't apply
    uv run python scripts/run_migrations.py --status    # list applied vs pending
    uv run python scripts/run_migrations.py --mark-applied 002_initial_schema.sql
        # Record a migration as applied WITHOUT running its SQL — for a database that
        # already has the matching schema from before this file existed (e.g. this
        # project's own transition off Alembic, where `alembic upgrade head` had already
        # created everything migrations/002-004 describe). Verify the schema actually
        # matches before using this; it does no verification itself.

To add a migration: drop a new `NNN_description.sql` file in migrations/ (next number,
zero-padded to 3 digits) with your CREATE/ALTER statements, then run this script.
"""

import argparse
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.core.config import settings  # noqa: E402

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def _connect() -> psycopg.Connection:
    # Plain psycopg DSN — deliberately not routed through SQLAlchemy's URL (this script has
    # no ORM dependency at all, matching the "just SQL files" spirit of this migration setup).
    #
    # autocommit=True is required for `with conn.transaction():` below to actually commit:
    # psycopg3 connections default to autocommit=False, which means the connection is
    # already inside an implicit transaction before `conn.transaction()` even runs — nesting
    # it there makes it a SAVEPOINT, not a real transaction, so its "commit" only releases
    # the savepoint. The outer implicit transaction is never committed, and everything it
    # did gets silently rolled back when the connection closes. With autocommit=True there
    # is no implicit outer transaction, so `conn.transaction()` opens and commits a real one.
    return psycopg.connect(
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        dbname=settings.POSTGRES_DB,
        autocommit=True,
    )


def _ensure_tracking_table(conn: psycopg.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            filename TEXT PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    conn.commit()


def _applied_filenames(conn: psycopg.Connection) -> set[str]:
    rows = conn.execute("SELECT filename FROM schema_migrations").fetchall()
    return {row[0] for row in rows}


def _pending_files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run", action="store_true", help="Print pending files, don't run them."
    )
    parser.add_argument(
        "--status", action="store_true", help="List applied vs pending, then exit."
    )
    parser.add_argument(
        "--mark-applied",
        metavar="FILENAME",
        help="Record this migration as applied without running its SQL.",
    )
    args = parser.parse_args()

    conn = _connect()
    _ensure_tracking_table(conn)
    applied = _applied_filenames(conn)
    all_files = _pending_files()
    pending = [f for f in all_files if f.name not in applied]

    if args.mark_applied:
        if args.mark_applied not in {f.name for f in all_files}:
            print(f"No such migration file: {args.mark_applied}", file=sys.stderr)
            sys.exit(1)
        conn.execute(
            "INSERT INTO schema_migrations (filename) VALUES (%s) ON CONFLICT DO NOTHING",
            (args.mark_applied,),
        )
        conn.commit()
        print(f"Marked {args.mark_applied} as applied (SQL not run).")
        return

    if args.status:
        for f in all_files:
            mark = "applied" if f.name in applied else "PENDING"
            print(f"[{mark:7}] {f.name}")
        return

    if not pending:
        print("Nothing to apply — schema is up to date.")
        return

    if args.dry_run:
        print("Would apply, in order:")
        for f in pending:
            print(f"  {f.name}")
        return

    for f in pending:
        print(f"Applying {f.name} ...")
        sql = f.read_text()
        try:
            with conn.transaction():
                conn.execute(sql)
                conn.execute(
                    "INSERT INTO schema_migrations (filename) VALUES (%s)", (f.name,)
                )
        except Exception:
            print(f"FAILED on {f.name} — nothing from this file was committed.", file=sys.stderr)
            raise
        print("  ok")

    print(f"Applied {len(pending)} migration(s).")


if __name__ == "__main__":
    main()
