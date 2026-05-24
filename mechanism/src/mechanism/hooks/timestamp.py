"""The `/hooks/timestamp` endpoint — temporal grounding on UserPromptSubmit.

Returns a one-line prose `additionalContext` saying when the user sent
this message and how long it's been since the previous one. Per-session
last-message-time lives in Redis (`SET ... GET`), one-week TTL.

First message of a session: no previous, so the second clause is
omitted entirely.
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

import logfire
from pydantic import BaseModel, ConfigDict, Field

from mechanism import clock
from mechanism.hooks import router
from mechanism.redis_client import get_redis_client

_LAST_MSG_TTL_SECONDS = 7 * 24 * 60 * 60  # one week


class HookEnvelope(BaseModel):
    """Subset of the Claude Code hook JSON envelope we care about."""

    session_id: str

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore")


class HookResponse(BaseModel):
    """The hook response shape Claude Code expects."""

    hook_specific_output: dict[str, str] = Field(serialization_alias="hookSpecificOutput")


@router.post("/timestamp")
async def timestamp(envelope: HookEnvelope) -> HookResponse:
    """Return a one-line timestamp note as additionalContext."""
    with logfire.span("hooks.timestamp {session_id}", session_id=envelope.session_id):
        redis_client = get_redis_client()
        now = clock.now()
        now_pso = clock.pso8601(now)

        key = f"last-msg:{envelope.session_id}"
        # Atomically: write the new timestamp, get back the previous (or None).
        previous_iso = await redis_client.set(
            key, now.isoformat(), ex=_LAST_MSG_TTL_SECONDS, get=True
        )

        if previous_iso is None:
            additional_context = f"The user sent this message on {now_pso}."
        else:
            previous = datetime.fromisoformat(previous_iso)
            gap = clock.elapsed(previous, now)
            additional_context = (
                f"The user sent this message on {now_pso}. "
                f"It has been {gap} since the previous message."
            )

        return HookResponse(
            hook_specific_output={
                "hookEventName": "UserPromptSubmit",
                "additionalContext": additional_context,
            }
        )
