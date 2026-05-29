"""Alembic migration environment for the mechanism database.

Migrations run synchronously through psycopg, even though the served app
talks asyncpg: a migration is a short-lived, strictly sequential script, so
sync is the natural shape — and SQLAlchemy/psycopg stay out of the runtime
image (they live in the `migrations` dependency group, not `[project]`).

The connection URL is sourced from the app's own ``DATABASE_URL`` setting,
not from ``alembic.ini``, so there is one source of truth and it fails loud
if unset. Migrations are hand-written as raw SQL via ``op.execute``, so there
is no ORM metadata to autogenerate against (``target_metadata`` stays None).
"""

from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import create_engine, pool
from sqlalchemy.engine import make_url

from alembic import context
from mechanism.settings import get_settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Hand-written migrations (raw SQL via op.execute); nothing to autogenerate.
target_metadata = None


def _migration_url() -> str:
    """Return the app's DATABASE_URL coerced to the sync psycopg driver.

    The app connects with asyncpg directly; SQLAlchemy/Alembic need a sync
    DBAPI, so the drivername is swapped to ``postgresql+psycopg`` against the
    same database. ``get_settings()`` is the single source of truth and raises
    if ``DATABASE_URL`` is unset.
    """
    url = make_url(str(get_settings().database_url)).set(drivername="postgresql+psycopg")
    return url.render_as_string(hide_password=False)


def run_migrations_offline() -> None:
    """Emit migrations as SQL to stdout without connecting (``--sql`` mode)."""
    context.configure(
        url=_migration_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect with a sync psycopg engine and run migrations against the DB."""
    connectable = create_engine(_migration_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
