"""Alembic environment — wired to the app's Settings and SQLAlchemy metadata.

Uses the sync psycopg driver (SQLALCHEMY_SYNC_DATABASE_URI) since Alembic's
migration runner is not async; the app itself uses asyncpg at runtime.
"""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import settings
from app.db.base_class import Base

# Import every model module so Base.metadata is fully populated before autogenerate runs.
import app.models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Deliberately NOT using config.set_main_option("sqlalchemy.url", ...) here: Alembic's Config
# stores that value in a ConfigParser, whose BasicInterpolation treats a bare '%' as the start
# of an interpolation token ('%(name)s'). A percent-encoded password (e.g. quote() turning '@'
# into '%40' — which is virtually every real-world password once special characters are
# involved) would raise "invalid interpolation syntax" the moment it's set. Building the engine
# straight from `settings` below skips ConfigParser entirely, so this can't recur.
target_metadata = Base.metadata


def include_object(object, name, type_, reflected, compare_to):
    """Skip PostGIS's own internal tables when autogenerating diffs."""
    if type_ == "table" and name in {"spatial_ref_sys"}:
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=settings.SQLALCHEMY_SYNC_DATABASE_URI,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(settings.SQLALCHEMY_SYNC_DATABASE_URI, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
