"""Asynchronous database helpers.

The async pool is lazily created on first use and lives for the lifetime
of the process. `get_pool()` is the single entry point — callers acquire
connections from the returned pool via `async with pool.acquire() as conn:`.
"""

from __future__ import annotations

import asyncpg
from pgvector.asyncpg import (  # pyright: ignore[reportMissingTypeStubs]
    register_vector,  # pyright: ignore[reportUnknownVariableType]
)

from mechanism.settings import get_settings

_pool: asyncpg.Pool | None = None


async def _init_connection(conn: asyncpg.Connection) -> None:
    """Per-connection setup: register pgvector against the extensions schema."""
    await register_vector(conn, schema="extensions")


async def get_pool() -> asyncpg.Pool:
    """Return the process-singleton asyncpg pool, creating it on first call.

    `server_settings={"search_path": "public, extensions"}` is passed
    as a connection-startup parameter, which survives asyncpg's
    between-borrow connection reset. Setting it via `SET search_path`
    in the init callback gets wiped on reset; this doesn't.

    Production pgvector lives in the `extensions` schema, so the
    operators (`<=>`, `<->`, `<#>`) and the `vector` type are there.
    Putting `extensions` on the search path lets SQL read naturally
    (`embedding <=> $1` instead of `OPERATOR(extensions.<=>)`).

    SET search_path doesn't validate that the schemas exist; it's a
    lookup hint, not an assertion. A future fork (Rosemary, etc.) whose
    DB has pgvector in `public` will simply find the operators there
    first and ignore the missing `extensions` entry.

    Application tables are still explicitly schema-qualified everywhere
    they're used (`cortex.memories`, `cortex.diary`, etc.) per the
    "read-what-runs" rule. This setting is scoped to extension intrinsics.
    """
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=str(get_settings().database_url),
            min_size=1,
            max_size=4,
            init=_init_connection,
            server_settings={"search_path": "public, extensions"},
        )
    return _pool


async def close_pool() -> None:
    """Close the singleton asyncpg pool if it's open. Called from the app lifespan."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
