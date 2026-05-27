"""The `reflection` tool — Stop-hook reflection reminder.

Fires every third turn, gated on a per-session turn counter in Redis
(7-day TTL). On firing turns, returns a Claude Code Stop-hook decision
envelope that keeps the turn open and surfaces the reminder text.
Returns None on non-firing turns and when ``stop_hook_active`` is True.
"""

from __future__ import annotations

import json
from typing import cast

import logfire
from fastmcp.tools.base import ToolResult
from mcp.types import TextContent, ToolAnnotations

from mechanism.mechanism.server import mcp
from mechanism.prompts import get_prompt
from mechanism.redis_client import get_redis_client

_TURN_TTL_SECONDS = 7 * 24 * 60 * 60  # one week

_REMINDER_TEXT = get_prompt("reflection_user")


def _gate(turn: int) -> bool:
    """Return True on turns 3, 6, 9, 12, ... — every third turn starting at 3."""
    return turn % 3 == 0


@mcp.tool(
    description=(
        "Stop-hook turn counter and reflection reminder. Fires every third "
        "turn with a between-turns reflection reminder, returning a "
        "block-decision that keeps the turn open. Returns no-op on "
        "non-firing turns or when stop_hook_active indicates we're already "
        "continuing from a prior block."
    ),
    annotations=ToolAnnotations(
        title="Reflection",
        readOnlyHint=False,  # writes the turn counter to Redis
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
async def reflection(
    session_id: str,
    stop_hook_active: bool = False,
) -> ToolResult | None:
    """Increment this session's turn counter; block-with-reason if the gate fires."""
    with logfire.span("reflection {session_id}", session_id=session_id):
        # Don't recurse: if Claude Code is already continuing because of a prior
        # block, let this turn end normally.
        if stop_hook_active:
            return None

        redis_client = get_redis_client()
        key = f"reflection:turn:{session_id}"

        # INCR on a missing key starts at 1. Atomic.
        turn = int(cast("int", await redis_client.incr(key)))
        await redis_client.expire(key, _TURN_TTL_SECONDS)

        if not _gate(turn):
            return None

        envelope = {"decision": "block", "reason": _REMINDER_TEXT}
        return ToolResult(
            content=[TextContent(type="text", text=json.dumps(envelope))],
        )
