"""Integration test for the `store_memory` MCP tool.

End-to-end via FastMCP's in-process client against the test stack. Asserts
that store_memory inserts a row in cortex.memories with the content we sent
and a non-null embedding.

In local dev this hits real Bifrost for the embedding call (which is the
intended design — see #10 conversation: real upstream in local, mocked in
CI). The LLM-mock fixture for CI is a separate piece of work.

Japanese content per the fluorescent-dye seed plan.
"""

from __future__ import annotations

from typing import Any

from fastmcp import Client

from mechanism.cortex import mcp
from mechanism.db import get_pool


async def test_store_memory_writes_row_with_embedding() -> None:
    """store_memory inserts a row in cortex.memories with content + embedding."""
    content = "今日は猫カフェでアルファに会った"  # "today I met Alpha at the cat café"

    async with Client(mcp) as client:
        result = await client.call_tool("store_memory", {"content": content})

    assert result.structured_content is not None
    payload: dict[str, Any] = result.structured_content
    new_id = int(payload["id"])
    assert new_id > 0
    assert isinstance(payload["created_at"], str)
    assert len(payload["created_at"]) > 0

    # Verify the row actually landed with content + a real embedding.
    sql = """
        SELECT content, embedding_qwen IS NOT NULL AS has_embedding
          FROM cortex.memories
         WHERE id = $1
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(sql, new_id)
    assert row is not None
    assert row["content"] == content
    assert row["has_embedding"] is True
