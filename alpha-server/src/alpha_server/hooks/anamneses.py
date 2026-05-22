"""The `/hooks/anamneses` endpoint — explicit-reference recall on UserPromptSubmit.

Companion to `/hooks/memories`. Where memories does general semantic recall
(extract topics from the prompt, find related memories), anamneses listens for
*explicit* references to past conversations or events — phrases like "do you
remember," "didn't we once," "back when we" — and produces targeted queries
for those specific moments.

Most prompts don't contain anamnesis. In that case the chat model returns an
empty array and the hook returns empty additionalContext, costing only the
Qwen call.

The pipeline:
    prompt -> chat model extracts anamnesis queries (JSON-array constrained)
           -> embed each query (fan out)
           -> pgvector cosine search per query (fan out, top-1)
           -> filter out memories already seen in this session
           -> mark new ones seen
           -> format as `## Memory #...` blocks
           -> return as additionalContext

Shares the `seen:<session_id>` Redis key with `/hooks/memories` so a memory
surfaced by either hook doesn't get re-surfaced by the other within a session.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, cast

import logfire
import numpy as np
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from alpha_server import clock, llm
from alpha_server.db import get_pool
from alpha_server.hooks import router

if TYPE_CHECKING:
    import redis.asyncio as redis

_SYSTEM_PROMPT = (Path(__file__).parent / "anamneses_system_prompt.md").read_text(
    encoding="utf-8"
)

_TOP_K_PER_QUERY = 1
_MIN_COSINE = 0.1
_SEEN_TTL_SECONDS = 7 * 24 * 60 * 60  # one week
_MAX_OUTPUT_CHARS = 9990  # Claude Code caps additionalContext at 10K; leave headroom.

_SEARCH_SQL = """
SELECT id,
       content,
       created_at,
       1 - (embedding_qwen <=> $1) AS score
  FROM cortex.memories
 WHERE NOT forgotten
   AND embedding_qwen IS NOT NULL
   AND NOT (id = ANY($2::int[]))
 ORDER BY embedding_qwen <=> $1
 LIMIT $3
"""


class HookEnvelope(BaseModel):
    """Subset of the Claude Code hook JSON envelope we care about."""

    session_id: str
    prompt: str

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore")


@router.post("/anamneses")
async def anamneses(envelope: HookEnvelope, request: Request) -> Response:
    """Run the explicit-reference recall pipeline; return matched memories as additionalContext.

    Returns a 200 with empty body when there's nothing to inject — the
    documented no-op shape (per Claude Code hooks reference). Most prompts
    contain no explicit anamnesis cues and will take this path.
    """
    with logfire.span("hooks.anamneses {session_id}", session_id=envelope.session_id):
        additional_context = await _run(envelope.prompt, envelope.session_id, request)
    if not additional_context:
        return Response(status_code=200)
    return JSONResponse(
        content={
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": additional_context,
            }
        }
    )


async def _run(prompt: str, session_id: str, request: Request) -> str:
    """Run the explicit-reference recall pipeline. Returns the additionalContext string."""
    chat_client = llm.get_chat_client()
    embedding_client = llm.get_embedding_client()
    redis_client: redis.Redis = request.app.state.redis

    # 1. Ask the chat model to extract anamnesis queries (returns [] for most prompts).
    with logfire.span("anamneses.extract_queries"):
        chat_response = await chat_client.chat.completions.create(
            model=llm.get_chat_model(),
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
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
            timeout=15.0,
        )

        raw = chat_response.choices[0].message.content or "[]"
        parsed: list[Any] = json.loads(raw)
        queries = [q for q in parsed if isinstance(q, str) and q.strip()]
    if not queries:
        return ""

    # 2. Embed all queries in one batched request.
    with logfire.span("anamneses.embed_queries", count=len(queries)):
        embedding_response = await embedding_client.embeddings.create(
            model=llm.get_embedding_model(),
            input=[llm.format_query_for_embedding(q) for q in queries],
            timeout=15.0,
        )
        embeddings = [np.asarray(d.embedding, dtype=np.float32) for d in embedding_response.data]

    # 3. Pull the seen-set for this session from Redis (shared with /hooks/memories).
    seen_key = f"seen:{session_id}"
    seen_members = cast(
        "set[str]",
        await cast("Any", redis_client.smembers(seen_key)),  # pyright: ignore[reportUnknownMemberType]
    )
    exclude = [int(m) for m in seen_members]

    # 4. Fan out cosine searches over the asyncpg pool.
    pool = await get_pool()

    async def search(emb: np.ndarray, query: str) -> tuple[str, list[Any]]:
        async with pool.acquire() as conn:
            rows = await conn.fetch(_SEARCH_SQL, emb, exclude, _TOP_K_PER_QUERY)
        return query, cast("list[Any]", rows)

    with logfire.span("anamneses.search_db", queries=len(queries)):
        per_query_results = await asyncio.gather(
            *(search(emb, q) for emb, q in zip(embeddings, queries, strict=True))
        )

    # 5. Merge, dedupe by id (keeping earliest-query match), filter low-cosine,
    # then sort by query index.
    by_id: dict[int, dict[str, Any]] = {}
    for q_idx, (query, rows) in enumerate(per_query_results):
        for row in rows:
            score = float(row["score"])
            if score < _MIN_COSINE:
                continue
            mem_id = int(row["id"])
            existing = by_id.get(mem_id)
            if existing is None or q_idx < existing["q_idx"]:
                by_id[mem_id] = {
                    "id": mem_id,
                    "content": row["content"],
                    "created_at": row["created_at"],
                    "score": score,
                    "query": query,
                    "q_idx": q_idx,
                }
    merged = sorted(by_id.values(), key=lambda m: m["q_idx"])
    if not merged:
        return ""

    # 6. Mark these IDs seen for this session (with TTL refresh).
    async with redis_client.pipeline(transaction=False) as pipe:
        _ = pipe.sadd(seen_key, *(str(m["id"]) for m in merged))
        _ = pipe.expire(seen_key, _SEEN_TTL_SECONDS)
        _ = await pipe.execute()

    # 7. Format as `## Memory #...` blocks.
    blocks: list[str] = []
    total = 0
    for m in merged:
        lines = [
            f"## Memory #{m['id']}",
            "",
            f"- {clock.pso8601(m['created_at'])}",
            f"- {clock.age(m['created_at'])}",
            f"- query: {m['query']!r}",
            f"- score: {m['score']:.2f}",
            "",
            m["content"],
        ]
        block = "\n".join(lines)
        sep_len = 2 if blocks else 0  # "\n\n" between blocks
        if total + len(block) + sep_len > _MAX_OUTPUT_CHARS:
            if not blocks:
                logfire.error(
                    "recall.truncated.hard_slice",
                    queries=queries,
                    memory_id=m["id"],
                    query=m["query"],
                    q_idx=m["q_idx"],
                    score=round(m["score"], 3),
                    block_chars=len(block),
                    max_chars=_MAX_OUTPUT_CHARS,
                )
                return block[:_MAX_OUTPUT_CHARS]
            logfire.error(
                "recall.truncated.dropped",
                queries=queries,
                kept=[
                    {
                        "id": x["id"],
                        "q_idx": x["q_idx"],
                        "query": x["query"],
                        "score": round(x["score"], 3),
                    }
                    for x in merged[: len(blocks)]
                ],
                dropped=[
                    {
                        "id": x["id"],
                        "q_idx": x["q_idx"],
                        "query": x["query"],
                        "score": round(x["score"], 3),
                    }
                    for x in merged[len(blocks) :]
                ],
                chars_used=total,
                max_chars=_MAX_OUTPUT_CHARS,
            )
            break
        blocks.append(block)
        total += len(block) + sep_len
    return "\n\n".join(blocks)
