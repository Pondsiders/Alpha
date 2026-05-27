"""Integration tests for the `timestamp` MCP tool.

Pins the wire shape (UserPromptSubmit hook envelope on both
``structured_content`` and ``content``) plus the two behavioral paths:
first-turn one-sentence output and subsequent-turn two-sentence output
with the elapsed-since-previous bucket from ``clock.elapsed``.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastmcp import Client
from mcp.types import TextContent

from mechanism import clock
from mechanism.mechanism import mcp
from mechanism.redis_client import get_redis_client


async def test_timestamp_returns_user_prompt_submit_envelope() -> None:
    """timestamp() returns a UserPromptSubmit hook envelope on both wire surfaces."""
    session_id = str(uuid.uuid4())

    async with Client(mcp) as client:
        result = await client.call_tool("timestamp", {"session_id": session_id})

    assert result.is_error is False

    assert result.structured_content is not None
    structured: dict[str, Any] = result.structured_content
    hook_output = structured["hookSpecificOutput"]
    assert hook_output["hookEventName"] == "UserPromptSubmit"
    additional_context = hook_output["additionalContext"]
    assert isinstance(additional_context, str)
    assert additional_context.startswith("The user sent this message on ")

    assert len(result.content) == 1
    block = result.content[0]
    assert isinstance(block, TextContent)
    assert block.type == "text"
    text_envelope = json.loads(block.text)
    assert text_envelope == structured


async def test_timestamp_first_turn_omits_elapsed_sentence() -> None:
    """On the first call for a session, only the 'sent on' line appears."""
    session_id = str(uuid.uuid4())

    async with Client(mcp) as client:
        result = await client.call_tool("timestamp", {"session_id": session_id})

    structured = result.structured_content
    assert structured is not None
    additional_context = structured["hookSpecificOutput"]["additionalContext"]
    assert "It has been" not in additional_context
    assert "since the previous message" not in additional_context


async def test_timestamp_second_turn_includes_elapsed_bucket() -> None:
    """When `last-msg:<session_id>` exists, the response adds the elapsed line."""
    session_id = str(uuid.uuid4())
    redis = get_redis_client()

    # Seed an earlier value 5 minutes ago so clock.elapsed lands in the
    # "5 minutes" bucket (< 60 minutes → "N minutes"). Stored as UTC ISO
    # to match what production now writes.
    earlier = clock.now().subtract(minutes=5)
    _ = await redis.set(f"last-msg:{session_id}", clock.utc_iso(earlier), ex=86400)

    async with Client(mcp) as client:
        result = await client.call_tool("timestamp", {"session_id": session_id})

    structured = result.structured_content
    assert structured is not None
    additional_context = structured["hookSpecificOutput"]["additionalContext"]
    assert "5 minutes" in additional_context
    assert additional_context.endswith("since the previous message.")
