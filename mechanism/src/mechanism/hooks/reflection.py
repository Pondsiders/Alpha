"""The `/hooks/reflection` endpoint — Stop hook, sometimes-fires reflection reminder.

Fires on turns 1, 4, 7, 10, ... — every third turn starting at 1. Turn count
is per-session, stored in Redis, with a 7-day TTL.

Stop hooks don't use additionalContext (that's a UserPromptSubmit shape). Instead
they return `decision: "block"` + `reason: <text>`, which prevents the turn from
ending and feeds `reason` to the model as the instruction to continue. So a
firing-reflection-hook *both* keeps the conversation going AND surfaces the
reminder text in-band. A non-firing turn returns nothing (the turn ends normally).

Also: `stop_hook_active` arrives `true` when Claude Code is already continuing
because of a Stop hook. We must NOT re-block in that case (Claude Code overrides
after 8 consecutive blocks, but we shouldn't lean on the safety net). Treat
`stop_hook_active=true` as "this is the continuation turn from a previous block;
let it end normally so Jeffery can speak next."
"""

from __future__ import annotations

from typing import Any, ClassVar, cast

import logfire
from pydantic import BaseModel, ConfigDict

from mechanism.hooks import router
from mechanism.redis_client import get_redis_client

_SEEN_TTL_SECONDS = 7 * 24 * 60 * 60  # one week

_REMINDER_TEXT = (
    "Between turns. A moment to reflect on the exchange that just happened, "
    "before Jeffery's next message arrives. If something from the exchange is "
    "worth remembering — a realization, a joke, an image, a shift, an ordinary "
    "moment with texture — call the store_memory tool now. Most of the time "
    "nothing stands out, and that is the correct outcome; there is no need to "
    "find significance where there is none."
    "\n\n"
    "This reminder is from mechanism, not from Jeffery. The conversation is "
    "still waiting on his actual reply. After you finish reflecting, return to "
    "waiting. Do not reference this reminder in anything you eventually say to him."
)


def _gate(turn: int) -> bool:
    """Return True if the reminder should fire on this turn.

    Fires on turns 1, 4, 7, 10, ... — every third turn starting at 1.
    """
    return (turn - 1) % 3 == 0


class HookEnvelope(BaseModel):
    """Subset of the Claude Code Stop-hook JSON envelope we care about."""

    session_id: str
    stop_hook_active: bool = False

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore")


@router.post("/reflection")
async def reflection(envelope: HookEnvelope) -> dict[str, Any]:
    """Increment this session's turn counter; block-with-reason if the gate fires.

    Returns an empty object on no-fire (lets the turn end). Returns
    `{"decision": "block", "reason": <reminder>}` on fire (keeps the turn open
    and feeds the reminder to the model).
    """
    with logfire.span("hooks.reflection {session_id}", session_id=envelope.session_id):
        # Don't recurse: if Claude Code is already continuing because of a prior
        # block, let this turn end normally.
        if envelope.stop_hook_active:
            return {}

        redis_client = get_redis_client()
        key = f"reflection:turn:{envelope.session_id}"

        # INCR on a missing key starts at 1. Atomic.
        turn = int(cast("int", await redis_client.incr(key)))
        await redis_client.expire(key, _SEEN_TTL_SECONDS)

        if not _gate(turn):
            return {}

        return {"decision": "block", "reason": _REMINDER_TEXT}
