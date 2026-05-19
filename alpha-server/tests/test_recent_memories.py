"""Integration test for `recent_memories` against a live dev database.

Requires Postgres reachable at the configured DATABASE_URL with cortex.memories
populated. Run via `uv run pytest`.
"""

from __future__ import annotations

from typing import Any

from fastmcp import Client

from alpha_server.cortex import mcp


async def test_recent_memories_returns_ascending_by_created_at() -> None:
    """Default call returns up to `limit` of the latest memories, oldest-first within the batch."""
    async with Client(mcp) as client:
        result = await client.call_tool("recent_memories", {"limit": 5})

    assert result.structured_content is not None
    memories: list[dict[str, Any]] = result.structured_content.get("result", [])
    assert isinstance(memories, list)
    assert len(memories) <= 5
    for m in memories:
        assert "id" in m
        assert "content" in m
        assert "created_at" in m
        assert "age" in m

    # IDs are monotonic in cortex.memories (serial primary key) and SELECT
    # by latest-N-then-reverse should leave them ascending.
    ids = [m["id"] for m in memories]
    assert ids == sorted(ids), f"expected ascending ids, got {ids}"
