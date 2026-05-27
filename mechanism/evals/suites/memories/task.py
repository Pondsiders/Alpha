"""Task function for the memories tool prompt eval.

`make_task(system_prompt)` returns an async callable suitable for
`dataset.evaluate_sync(task)`. The callable mirrors the production chat
call in `mechanism.mechanism.memories._run` step 1 — same model, same
sampling parameters, same JSON-schema response constraint, same parsing
logic. *If you change the production tool's chat parameters, change
them here too.*

The system prompt is injected at task-construction time rather than
read from disk inside the call. This lets the harness A/B different
prompt versions (v1 baseline, v2 candidate) without touching this file.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from mechanism import llm


def make_task(system_prompt: str) -> Callable[[str], Awaitable[list[str]]]:
    """Return an async task fn that calls Qwen with the given system prompt.

    The returned fn matches the signature pydantic-evals expects for
    `dataset.evaluate_sync(task)`: a single `message: str` argument
    returning the model's parsed list of query strings.
    """

    async def query_qwen(message: str) -> list[str]:
        client = llm.get_chat_client()
        response = await client.chat.completions.create(
            model=llm.get_chat_model(),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ],
            temperature=0.7,
            top_p=0.8,
            presence_penalty=1.5,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "queries",
                    "strict": True,
                    "schema": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
            extra_body={
                "top_k": 20,
                "min_p": 0.0,
                "repetition_penalty": 1.0,
            },
            timeout=30.0,
        )
        raw = response.choices[0].message.content or "[]"
        parsed: list[Any] = json.loads(raw)
        return [q for q in parsed if isinstance(q, str) and q.strip()]

    return query_qwen
