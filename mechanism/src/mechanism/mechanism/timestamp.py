"""The `timestamp` tool — temporal grounding for UserPromptSubmit.

Minimal prototype: returns the Claude Code hook output schema with a
one-line "was sent at" `additionalContext`. No Redis dependence, no
"elapsed since previous message" clause — those come back when this
shape is validated.

Returns a plain dict, not a primitive string or a Pydantic model.
FastMCP wraps primitive returns in `{"result": ...}` structured content,
which Claude Code's hook layer doesn't recognize. Pydantic models with
`serialization_alias` need `by_alias=True` at dump time, which FastMCP
doesn't promise. A plain dict with string-literal camelCase keys passes
through FastMCP cleanly: the keys are clearly Claude-Code's schema, not
our Python convention.
"""

from __future__ import annotations

from mcp.types import ToolAnnotations

from mechanism import clock
from mechanism.mechanism.server import mcp


@mcp.tool(
    description=(
        "Return temporal grounding for the current user prompt as a "
        "UserPromptSubmit hook response. Sets `additionalContext` to a "
        "one-line 'was sent at' string."
    ),
    annotations=ToolAnnotations(
        title="Timestamp",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
async def timestamp() -> dict[str, dict[str, str]]:
    """Return a UserPromptSubmit hook response with a one-line timestamp note."""
    return {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": (
                f"The user sent this message on {clock.pso8601(clock.now())}."
            ),
        }
    }
