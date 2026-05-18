"""The `execute_query` tool — read-only SQL against the cortex database."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

import numpy as np
from mcp.types import ToolAnnotations

from alpha_server import clock
from alpha_server.cortex.server import mcp
from alpha_server.db import get_pool

# Statement timeout — caps any individual query at 5 seconds. Expensive
# queries fail loudly rather than blocking the pool. The READ ONLY
# transaction enforces the no-writes promise at the Postgres level;
# this is the expense-protection complement.
_STATEMENT_TIMEOUT_MS = 5000


def _jsonable(value: Any) -> Any:
    """Coerce asyncpg values into JSON-friendly shapes.

    - datetime → PSO-8601 string (consistent with our tool surface)
    - bytes → omitted (`<bytes len=N>`)
    - lists of floats with len > 64 → omitted (`<vector len=N>`); covers
      pgvector embedding columns without ballooning the response
    - everything else → returned as-is
    """
    if isinstance(value, datetime):
        return clock.pso8601(value)
    if isinstance(value, bytes):
        return f"<bytes len={len(value)}>"
    if isinstance(value, np.ndarray):
        return f"<vector len={value.size}>"
    if isinstance(value, list):
        items = cast("list[Any]", value)
        if len(items) > 64 and all(isinstance(x, float) for x in items):
            return f"<vector len={len(items)}>"
        return items
    return value


@mcp.tool(
    description=(
        "Execute a read-only SQL query against the cortex database. "
        "Use get_schema first to see what tables and columns exist. "
        "The transaction is READ ONLY at the Postgres level; writes "
        "fail with error 25006. Statement timeout: 5 seconds."
    ),
    annotations=ToolAnnotations(
        title="Execute query",
        readOnlyHint=True,
        openWorldHint=False,
    ),
    meta={"anthropic/maxResultSizeChars": 400000},
)
async def execute_query(sql: str) -> list[dict[str, Any]]:
    """Run sql in a read-only transaction; return rows as a list of dicts.

    Args:
        sql: A SQL query. Any DDL/DML inside fails with Postgres error
            25006 (cannot execute X in a read-only transaction).

    Returns:
        List of rows, each a dict from column name to value. Datetimes
        are PSO-8601 strings; pgvector embeddings are omitted with a
        short summary string; bytes are summarized.
    """
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction(readonly=True):
        _ = await conn.execute(f"SET LOCAL statement_timeout = {_STATEMENT_TIMEOUT_MS}")
        rows = await conn.fetch(sql)

    return [{key: _jsonable(value) for key, value in row.items()} for row in rows]
