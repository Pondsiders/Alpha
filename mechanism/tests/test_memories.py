"""Integration tests for the `memories` MCP tool.

Pins the wire shape for two paths:

- Match: ``structured_content`` is the UserPromptSubmit hook envelope
  ``{"hookSpecificOutput": {"hookEventName": ..., "additionalContext": ...}}``;
  ``content`` carries the same envelope as a JSON-encoded ``TextContent``.
- No-op: ``content=[]``, ``structured_content=None``.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from fastmcp import Client
from mcp.types import TextContent
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice

from mechanism.mechanism import mcp


async def test_memories_match_returns_user_prompt_submit_envelope(
    seeded: None,  # pyright: ignore[reportUnusedParameter]
    mock_llm: dict[str, list[dict[str, Any]]],
) -> None:
    """memories() returns a UserPromptSubmit hook envelope on both wire surfaces."""
    session_id = str(uuid.uuid4())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "memories",
            {"prompt": "tell me about cat cafés", "session_id": session_id},
        )

    assert result.is_error is False
    assert len(mock_llm["chat_calls"]) == 1
    assert len(mock_llm["embed_calls"]) == 1

    assert result.structured_content is not None
    structured: dict[str, Any] = result.structured_content
    hook_output = structured["hookSpecificOutput"]
    assert hook_output["hookEventName"] == "UserPromptSubmit"
    additional_context = hook_output["additionalContext"]
    assert isinstance(additional_context, str)
    assert additional_context.startswith("## Memory #")

    assert len(result.content) == 1
    block = result.content[0]
    assert isinstance(block, TextContent)
    assert block.type == "text"
    text_envelope = json.loads(block.text)
    assert text_envelope == structured


async def test_memories_no_match_returns_empty_mcp_response(
    seeded: None,  # pyright: ignore[reportUnusedParameter]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """memories() returns content=[] and structured_content=None when chat extracts no queries."""
    from mechanism import llm

    async def empty_chat(**_kwargs: Any) -> ChatCompletion:
        return ChatCompletion(
            id="fake-chatcmpl",
            object="chat.completion",
            created=0,
            model="fake-chat-model",
            choices=[
                Choice(
                    index=0,
                    finish_reason="stop",
                    message=ChatCompletionMessage(role="assistant", content="[]"),
                )
            ],
        )

    monkeypatch.setattr(llm.get_chat_client().chat.completions, "create", empty_chat)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "memories",
            {"prompt": "no recall cues here", "session_id": str(uuid.uuid4())},
        )

    assert result.is_error is False
    assert result.content == []
    assert result.structured_content is None


async def test_memories_slash_command_short_circuits(
    seeded: None,  # pyright: ignore[reportUnusedParameter]
    mock_llm: dict[str, list[dict[str, Any]]],
) -> None:
    """memories() no-ops without touching the LLM when the prompt starts with '/'."""
    async with Client(mcp) as client:
        result = await client.call_tool(
            "memories",
            {"prompt": "/compact please", "session_id": str(uuid.uuid4())},
        )

    assert result.is_error is False
    assert result.content == []
    assert result.structured_content is None
    assert mock_llm["chat_calls"] == []
    assert mock_llm["embed_calls"] == []
