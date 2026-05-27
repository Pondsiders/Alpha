"""The `timestamp` tool — temporal grounding for UserPromptSubmit.

Returns a Claude Code UserPromptSubmit hook envelope. On the first turn
of a session the envelope carries just the "sent on" line; on subsequent
turns it adds a second sentence with the elapsed time since the previous
message, using `last-msg:<session_id>` as the per-session key.
"""

from __future__ import annotations

import logfire
from mcp.types import ToolAnnotations

from mechanism import clock
from mechanism.mechanism.server import mcp
from mechanism.redis_client import get_redis_client

_LAST_MSG_TTL_SECONDS = 24 * 60 * 60
"""TTL on `last-msg:<session_id>`. Sessions don't roll over days, so the
key expires on the same seam — dead sessions don't accumulate."""


@mcp.tool(
    description=(
        "Return temporal grounding for the current user prompt as a "
        "UserPromptSubmit hook response. Sets `additionalContext` to a "
        "'sent on' line, plus an elapsed-since-previous-message line on "
        "every turn after the first of the session."
    ),
    annotations=ToolAnnotations(
        title="Timestamp",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
    meta={"anthropic/alwaysLoad": True},
)
async def timestamp(session_id: str) -> dict[str, dict[str, str]]:
    """Return a UserPromptSubmit hook response with sent-on (+elapsed) lines."""
    with logfire.span("timestamp {session_id}", session_id=session_id):
        redis = get_redis_client()
        now = clock.now()
        key = f"last-msg:{session_id}"

        # Atomic read-and-update: write the new timestamp (as UTC ISO,
        # so storage matches the wire/Postgres convention — carry the
        # universal, render the local), return the old one or None if
        # this is the first turn. Single round trip; no window between
        # read and write where the value could be stale.
        old_iso: str | None = await redis.set(
            key, clock.utc_iso(now), ex=_LAST_MSG_TTL_SECONDS, get=True
        )

        sent_line = f"The user sent this message on {clock.pso8601(now)}."
        if old_iso is None:
            additional_context = sent_line
        else:
            earlier = clock.from_iso(old_iso)
            ago = clock.elapsed(earlier, now)
            additional_context = f"{sent_line} It has been {ago} since the previous message."

    return {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": additional_context,
        }
    }
