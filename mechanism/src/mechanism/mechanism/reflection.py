"""The `reflection` tool — Stop hook, sometimes-fires reflection reminder.

Port of the `/hooks/reflection` HTTP handler to an MCP tool on the
mechanism server. Stop hooks have a different envelope from
UserPromptSubmit hooks: they don't use ``additionalContext``; instead
they return ``{"decision": "block", "reason": <text>}`` to prevent the
turn from ending and feed ``reason`` to the model as the instruction to
continue. A firing reflection hook *both* keeps the conversation going
AND surfaces the reminder text in-band.

Fires on turns 1, 4, 7, 10, ... — every third turn starting at 1. Turn
count is per-session, stored in Redis, with a 7-day TTL.

Hook input includes ``stop_hook_active`` (true when Claude Code is
already continuing because of a prior Stop block). Must NOT re-block in
that case — Claude Code overrides after 8 consecutive blocks, but we
shouldn't lean on the safety net. The hook config wires this in via
``${stop_hook_active}`` substitution.

Returns ``None`` (empty response) on no-fire or when stop_hook_active is
true; returns the block-decision dict on fire.
"""

from __future__ import annotations

from typing import cast

import logfire
from mcp.types import ToolAnnotations

from mechanism.mechanism.server import mcp
from mechanism.prompts import get_prompt
from mechanism.redis_client import get_redis_client

_TURN_TTL_SECONDS = 7 * 24 * 60 * 60  # one week

_REMINDER_TEXT = get_prompt("reflection_user")


def _gate(turn: int) -> bool:
    """Return True if the reminder should fire on this turn.

    Fires on turns 1, 4, 7, 10, ... — every third turn starting at 1.
    """
    return (turn - 1) % 3 == 0


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
) -> dict[str, str] | None:
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

        return {"decision": "block", "reason": _REMINDER_TEXT}
