"""The `add_to_diary` tool — append an entry to today's diary page."""

from __future__ import annotations

from mcp.types import ToolAnnotations

from mechanism import clock
from mechanism.cortex.models import DiaryResult
from mechanism.cortex.server import mcp
from mechanism.db import get_pool

_INSERT_SQL = """
INSERT INTO cortex.diary (content, created_at)
VALUES ($1, $2)
RETURNING id, created_at
"""


@mcp.tool(
    description=(
        "Append an entry to today's diary page. Today's page can contain many "
        "entries; this tool appends one more."
    ),
    annotations=ToolAnnotations(
        title="Add to diary",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
    meta={"anthropic/alwaysLoad": True},
)
async def add_to_diary(content: str) -> DiaryResult:
    """Insert a row into cortex.diary with the given content.

    Args:
        content: The diary entry text to append.

    Returns:
        The id and timestamp of the newly-stored entry.
    """
    pool = await get_pool()
    now = clock.now()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_INSERT_SQL, content, now)
    if row is None:
        msg = "INSERT INTO cortex.diary did not RETURNING a row"
        raise RuntimeError(msg)
    return DiaryResult(
        id=row["id"],
        created_at=clock.pso8601(row["created_at"]),
    )
