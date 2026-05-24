"""Process-singleton async Redis client.

Hook handlers — soon hook MCP tools — need Redis for per-session state:

- ``last-msg:<session_id>`` — timestamp hook's previous-message timestamp
- ``seen:<session_id>`` — memories hook's recall-dedupe set
- ``reflection:turn:<session_id>`` — reflection hook's turn counter

When hooks ran under FastAPI, the Redis client lived on
``app.state.redis``, opened in the FastAPI lifespan. Under the Starlette
parent + FastMCP serving shape, MCP-tool hooks don't have FastAPI-request
scope. This module follows the same lazy-singleton pattern as ``db.py``
and ``llm.py``.
"""

from __future__ import annotations

import redis.asyncio as redis

from mechanism.settings import get_settings

_client: redis.Redis | None = None


def get_redis_client() -> redis.Redis:
    """Return the process-singleton async Redis client, opening on first call."""
    global _client
    if _client is None:
        _client = redis.from_url(str(get_settings().redis_url), decode_responses=True)
    return _client


async def close_redis_client() -> None:
    """Close the singleton Redis client if it's open. Called from the app lifespan."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
