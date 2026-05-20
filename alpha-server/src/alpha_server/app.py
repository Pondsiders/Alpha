"""FastAPI application factory.

Run with:
    uv run uvicorn alpha_server.app:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import redis.asyncio as redis
from fastapi import FastAPI

from alpha_server.cortex import mcp

# Side-effect imports register handlers against the shared hooks router.
from alpha_server.hooks import (
    memories,  # noqa: F401  # pyright: ignore[reportUnusedImport]
    reflection,  # noqa: F401  # pyright: ignore[reportUnusedImport]
    timestamp,  # noqa: F401  # pyright: ignore[reportUnusedImport]
)
from alpha_server.hooks import router as hooks_router
from alpha_server.settings import get_settings

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

_cortex_app = mcp.http_app(path="/mcp")


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Open long-lived per-request state and compose the Cortex MCP lifespan.

    Born once at startup, lives for the process lifetime:
    - redis client (seen-cache for the memories hook)

    The MCP session manager also needs to start before requests arrive at
    the mounted sub-app; without this hand-off, mounted tool calls hang.

    LLM clients and the database pool are lazy module-level singletons
    (see `llm.py` and `db.py`); they don't need lifespan involvement.
    """
    settings = get_settings()

    app.state.redis = redis.from_url(str(settings.redis_url), decode_responses=True)

    try:
        async with _cortex_app.lifespan(app):
            yield
    finally:
        await app.state.redis.aclose()


app = FastAPI(lifespan=_lifespan)
app.mount("/cortex", _cortex_app)
app.include_router(hooks_router, prefix="/hooks")


@app.get("/livez")
async def livez() -> dict[str, str]:
    """Process-up health check. Trivially true if FastAPI is responding."""
    return {"status": "ok"}
