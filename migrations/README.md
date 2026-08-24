# Database migrations

Plain `.sql` files, applied in filename order — no Alembic, no autogenerate, no ORM
dependency. This is deliberate: schema changes are written by hand as real DDL, reviewed as
real DDL in PRs, and applied by a runner with no framework magic in between.

## Applying migrations

```bash
make migrate           # apply every pending migration, in order
make migrate-status    # show which migrations are applied vs pending
```

Equivalent direct form: `uv run python scripts/run_migrations.py [--dry-run|--status]`.

Applied filenames are tracked in a `schema_migrations` table (created automatically on
first run). Re-running `make migrate` after everything is applied is a safe no-op.

## Adding a new migration

1. Create a new file: `NNN_short_description.sql`, where `NNN` is the next number,
   zero-padded to 3 digits (check the highest existing number first).
2. Write plain SQL: `CREATE TABLE`, `ALTER TABLE ... ADD COLUMN`, `CREATE INDEX`, etc.
   Wrap multi-statement changes that must succeed or fail together on your own judgment —
   the runner already wraps each *file* in one transaction, so anything that must be
   atomic just needs to live in the same file.
3. If the change adds/modifies a column, table, or enum that the app's SQLAlchemy models
   (`app/models/*.py`) read or write, update the matching model in the same PR — the model
   layer is not derived from these files (there's no autogenerate), so the two are kept in
   sync by hand.
4. Run `make migrate` locally against your dev database to verify it applies cleanly
   before committing.
5. Never edit a migration file that has already been merged/applied anywhere — add a new
   one instead, even to fix a mistake in a previous file. Editing an applied file's
   contents means different environments end up with different schemas despite agreeing
   on "migration 004 is applied."

## Current migrations

| File | What it does |
|---|---|
| `001_extensions.sql` | PostGIS + uuid-ossp extensions (already provisioned by the Docker Postgres image; this file exists for non-Docker Postgres). |
| `002_initial_schema.sql` | The full baseline schema: users, patients, professionals, bookings/offers/visits, payments/wallet, reviews, support tickets, notifications, devices, coupons. |
| `003_add_super_admin_role.sql` | Adds `SUPER_ADMIN` to the `user_role` enum, for the Next.js Super Admin portal. |
| `004_frontend_schema_additions.sql` | Waitlist signups, contact inquiries, patient↔nurse messaging, platform settings, and a handful of registration-time profile fields (qualifications, certifications, preferred contact method, free-text address, experience description, emergency contact relationship). |

See `docs/DATABASE_TABLES.md` for a full table-by-table reference of the resulting schema.

## Why not Alembic

This project previously used Alembic. It was replaced with this plain-SQL setup: schema
changes are authored directly as SQL (no autogenerate diffing against ORM models to
review/trust), and applying a migration has no dependency on the app's Python import graph
at all — only `psycopg` and the DB connection settings.
