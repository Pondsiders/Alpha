"""Integration test for `POST /hooks/anamneses`.

Sibling of `/hooks/memories` — same pipeline shape, different system prompt
(anamneses is tuned to extract explicit-reference queries like "do you
remember," "didn't we once"). Both expect the same chat-response shape and
both follow the same path: extract → embed → search → format.

This test pins the same plumbing contract as test_hooks_memories: 200 with
empty body on the no-recall path, chat got the prompt unchanged, embed got
the queries the chat returned with the Qwen `Instruct:` wrapping.
"""

from __future__ import annotations

import uuid
from typing import Any

from httpx import AsyncClient


async def test_anamneses_hook_chains_chat_embed_search(
    hooks_client: AsyncClient,
    mock_llm: dict[str, list[dict[str, Any]]],
) -> None:
    """Anamneses hook drives chat → embed → search end-to-end; empty DB → no-op response."""
    session_id = str(uuid.uuid4())
    prompt = "didn't we once talk about the duckpond clang?"

    resp = await hooks_client.post(
        "/hooks/anamneses",
        json={"session_id": session_id, "prompt": prompt},
    )

    # Empty cortex.memories → empty additionalContext → documented no-op:
    # 200 with empty body (per the hook's `Response(status_code=200)` path).
    assert resp.status_code == 200
    assert resp.content == b""

    # Chat was called exactly once with our prompt as the final user message.
    assert len(mock_llm["chat_calls"]) == 1
    messages = mock_llm["chat_calls"][0]["messages"]
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"] == prompt

    # Embed was called exactly once with the two queries from the canned
    # chat response, each wrapped by format_query_for_embedding.
    assert len(mock_llm["embed_calls"]) == 1
    embed_input = mock_llm["embed_calls"][0]["input"]
    assert isinstance(embed_input, list)
    assert len(embed_input) == 2  # pyright: ignore[reportUnknownArgumentType]
    assert "Instruct:" in embed_input[0]
    assert "Query:test query alpha" in embed_input[0]
    assert "Query:test query beta" in embed_input[1]
