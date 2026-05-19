"""The `recent_memories` tool — return the latest N memories, oldest-first within the batch."""

from __future__ import annotations

from typing import Annotated

from mcp.types import ToolAnnotations
from pydantic import Field

from alpha_server import clock
from alpha_server.cortex.models import Memory
from alpha_server.cortex.server import mcp
from alpha_server.db import get_pool

_SELECT = """
SELECT id, content, created_at
  FROM cortex.memories
 WHERE NOT forgotten
 ORDER BY created_at DESC
 LIMIT $1
"""


@mcp.tool(
    description=(
        "Return the latest N memories, ordered oldest-first within the batch "
        "(so you read the arc forward in time, the way you lived it). Use "
        "this for orientation — 'what was on my mind most recently?' — when "
        "you don't have a search query."
    ),
    annotations=ToolAnnotations(
        title="Recent memories",
        readOnlyHint=True,
        openWorldHint=False,
    ),
    meta={"anthropic/maxResultSizeChars": 400000},
)
async def recent_memories(
    limit: Annotated[
        int,
        Field(ge=1, le=100, description="Maximum number of memories to return."),
    ] = 10,
) -> list[Memory]:
    """Return up to `limit` of the latest memories, oldest-first within the batch.

    `limit` selects the latest N; the returned list reads forward in time
    (oldest at index 0, newest at index -1).

    Args:
        limit: Maximum memories to return (1..100).

    Returns:
        Memories ordered oldest-first within the latest-N batch. Empty list
        if cortex.memories is empty.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(_SELECT, limit)

    # SQL orders DESC so LIMIT selects the latest N. Reverse here so the
    # returned list reads forward-chronologically.
    return [
        Memory(
            id=row["id"],
            content=row["content"],
            created_at=clock.pso8601(row["created_at"]),
            age=clock.age(row["created_at"]),
        )
        for row in reversed(rows)
    ]
