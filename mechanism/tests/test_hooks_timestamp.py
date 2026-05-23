"""Integration test for `POST /hooks/timestamp`.

Returns an `additionalContext` string saying when the user sent the message.
On the first call for a session, that's all it says. On subsequent calls,
the context is extended with a "since the previous message" gap clause.

The brittle assertion pins the *behavior* (gap clause appended on the second
call) without pinning the *wording* — if we ever change the exact text of
either clause this test still passes; if we ever stop emitting the gap
clause on subsequent calls, this test breaks.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient


async def test_timestamp_extends_context_on_subsequent_calls(hooks_client: AsyncClient) -> None:
    """First call returns timestamp grounding; second call extends it with a gap clause."""
    session_id = str(uuid.uuid4())

    # First call for this session: establishes the last-msg key in Redis.
    resp1 = await hooks_client.post("/hooks/timestamp", json={"session_id": session_id})
    assert resp1.status_code == 200
    output1 = resp1.json()["hookSpecificOutput"]
    assert output1["hookEventName"] == "UserPromptSubmit"
    context1 = output1["additionalContext"]
    assert context1, "additionalContext should be non-empty on first call"

    # Second call, same session: should add a gap-since-previous clause.
    resp2 = await hooks_client.post("/hooks/timestamp", json={"session_id": session_id})
    assert resp2.status_code == 200
    output2 = resp2.json()["hookSpecificOutput"]
    assert output2["hookEventName"] == "UserPromptSubmit"
    context2 = output2["additionalContext"]

    # Structural contract, not a language assertion: subsequent calls
    # extend the context with a gap clause, so context2 is strictly longer.
    assert len(context2) > len(context1), (
        f"expected second call to add a gap clause; "
        f"got context1={context1!r} context2={context2!r}"
    )
