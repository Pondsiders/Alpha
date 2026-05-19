"""The `search_memories` tool — recall by semantic similarity or full-text index."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Literal

import numpy as np
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from alpha_server import clock, llm
from alpha_server.cortex.models import SearchHit, SearchMemoriesResult
from alpha_server.cortex.server import mcp
from alpha_server.db import get_pool

if TYPE_CHECKING:
    from datetime import datetime

_SEMANTIC_SELECT = """
SELECT id,
       content,
       created_at,
       1 - (embedding_qwen <=> $1) AS score
  FROM cortex.memories
 WHERE NOT forgotten
   AND embedding_qwen IS NOT NULL
"""

_SEMANTIC_ORDER = " ORDER BY embedding_qwen <=> $1 LIMIT "

_INDEX_SELECT = """
SELECT id,
       content,
       created_at,
       ts_rank_cd(content_tsv, query) AS score
  FROM cortex.memories,
       plainto_tsquery('english', $1) AS query
 WHERE NOT forgotten
   AND content_tsv @@ query
"""

_INDEX_ORDER = " ORDER BY score DESC LIMIT "


def _parse_when(value: str, *, label: str) -> datetime:
    """Parse a date/time string or raise ToolError with a label."""
    parsed = clock.parse_when(value)
    if parsed is None:
        msg = f"could not parse {label}={value!r} as a date"
        raise ToolError(msg)
    return parsed


@mcp.tool(
    description=(
        "Search your memories. (Diary pages are not searchable.)\n"
        "Two modes:\n"
        "- mode='semantic': cosine similarity\n"
        "- mode='index': Postgres full-text search; scores are raw ts_rank_cd. "
        "Multi-word queries are AND'd; terms are English-stemmed.\n"
        "Scores are relative within a result set and are not comparable "
        "between result sets.\n"
        "Optional since/until are parsed by the dateparser library, resolved "
        "in the server's configured timezone."
    ),
    annotations=ToolAnnotations(
        title="Search memories",
        readOnlyHint=True,
        openWorldHint=False,
    ),
    meta={"anthropic/maxResultSizeChars": 400000},
)
async def search_memories(
    mode: Literal["semantic", "index"],
    query: Annotated[str, Field(min_length=1, description="The search text. Must be non-empty.")],
    since: Annotated[
        str | None,
        Field(description="Lower bound on created_at, inclusive. Optional."),
    ] = None,
    until: Annotated[
        str | None,
        Field(description="Upper bound on created_at, exclusive. Optional."),
    ] = None,
    limit: Annotated[
        int,
        Field(ge=1, le=100, description="Maximum number of hits to return."),
    ] = 10,
) -> SearchMemoriesResult:
    """Recall memories matching `query` under the chosen mode.

    Args:
        mode: 'semantic' (cosine over the stored embedding) or 'index' (Postgres FTS).
        query: The search text (must be non-empty).
        since: Optional lower bound on created_at (inclusive).
        until: Optional upper bound on created_at (exclusive).
        limit: Maximum hits to return (1..100).

    Returns:
        A SearchMemoriesResult echoing mode and query, with hits ordered by
        descending score. `hits` is empty if nothing matches.
    """
    params: list[object]
    if mode == "semantic":
        response = await llm.get_embedding_client().embeddings.create(
            model=llm.get_embedding_model(),
            input=[llm.format_query_for_embedding(query)],
            timeout=15.0,
        )
        emb = np.asarray(response.data[0].embedding, dtype=np.float32)
        sql_parts = [_SEMANTIC_SELECT]
        params = [emb]
        order_clause = _SEMANTIC_ORDER
    else:
        sql_parts = [_INDEX_SELECT]
        params = [query]
        order_clause = _INDEX_ORDER

    if since is not None:
        params.append(_parse_when(since, label="since"))
        sql_parts.append(f" AND created_at >= ${len(params)}")
    if until is not None:
        params.append(_parse_when(until, label="until"))
        sql_parts.append(f" AND created_at < ${len(params)}")

    params.append(limit)
    sql_parts.append(f"{order_clause}${len(params)}")
    sql = "".join(sql_parts)

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *params)

    hits = [
        SearchHit(
            id=row["id"],
            content=row["content"],
            created_at=clock.pso8601(row["created_at"]),
            age=clock.age(row["created_at"]),
            score=float(row["score"]),
        )
        for row in rows
    ]
    return SearchMemoriesResult(mode=mode, query=query, hits=hits)
