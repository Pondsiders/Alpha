"""Integration test for the `get_memory` MCP tool.

Fetches a known seeded memory by id and asserts the returned shape matches
the seed row verbatim. With the per-test TRUNCATE...RESTART IDENTITY plus the
seeded fixture, the first seed memory is reliably id=1: the cat-café opener.
"""

from __future__ import annotations

from typing import Any

from fastmcp import Client

from mechanism.cortex import mcp


async def test_get_memory_returns_matching_seed_row(
    seeded: None,  # pyright: ignore[reportUnusedParameter]
) -> None:
    """get_memory(1) returns the first seeded memory with full Memory shape."""
    async with Client(mcp) as client:
        result = await client.call_tool("get_memory", {"memory_id": 1})

    assert result.structured_content is not None
    memory: dict[str, Any] = result.structured_content
    assert memory["id"] == 1
    assert memory["content"] == "今日は猫カフェに行きました。"
    # created_at and age are time-dependent; assert presence + non-empty.
    assert isinstance(memory["created_at"], str)
    assert memory["created_at"]
    assert isinstance(memory["age"], str)
    assert memory["age"]
