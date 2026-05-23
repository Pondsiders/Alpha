"""FastAPI application factory.

Run with:
    uv run uvicorn mechanism.app:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

from contextlib import AsyncExitStack, asynccontextmanager
from typing import TYPE_CHECKING

import logfire
import redis.asyncio as redis
from fastapi import FastAPI

from mechanism.cortex import mcp as cortex_mcp

# Side-effect imports register handlers against the shared hooks router.
from mechanism.hooks import (
    anamneses,  # noqa: F401  # pyright: ignore[reportUnusedImport]
    memories,  # noqa: F401  # pyright: ignore[reportUnusedImport]
    reflection,  # noqa: F401  # pyright: ignore[reportUnusedImport]
    timestamp,  # noqa: F401  # pyright: ignore[reportUnusedImport]
)
from mechanism.hooks import router as hooks_router
from mechanism.origin_validation import OriginValidationMiddleware
from mechanism.settings import get_settings
from mechanism.utils import mcp as utils_mcp

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

_cortex_app = cortex_mcp.http_app(path="/mcp")
_utils_app = utils_mcp.http_app(path="/mcp")


def _scrubbing_callback(match: logfire.ScrubMatch) -> str | None:
    """Whitelist ``session_id`` from Logfire's default scrubbing.

    Logfire's default patterns include ``session``, which matches our
    ``session_id`` span attribute. The Claude Code session UUID isn't
    sensitive on its own, and it's the only join key we have for
    cross-referencing mechanism traces with Claude Code's separate
    OTel trace stream and Bifrost logs.

    Other ``session``-pattern matches stay scrubbed; this is surgical.
    """
    if (
        match.path
        and match.path[-1] == "session_id"
        and match.pattern_match.group(0).lower() == "session"
    ):
        return match.value
    return None


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Open long-lived per-request state and compose the mounted MCP lifespans.

    Born once at startup, lives for the process lifetime:
    - redis client (seen-cache for the memories hook)

    The MCP session managers also need to start before requests arrive at
    the mounted sub-apps; without this hand-off, mounted tool calls hang.
    `AsyncExitStack` composes each sub-app's lifespan so adding another
    mounted MCP server is a single `enter_async_context` line.

    LLM clients and the database pool are lazy module-level singletons
    (see `llm.py` and `db.py`); they don't need lifespan involvement.
    """
    settings = get_settings()

    _ = logfire.configure(
        send_to_logfire="if-token-present",
        token=settings.logfire_token,
        service_name=settings.otel_service_name,
        scrubbing=logfire.ScrubbingOptions(callback=_scrubbing_callback),
    )
    _ = logfire.instrument_fastapi(app)
    logfire.instrument_httpx()
    logfire.instrument_asyncpg()
    _ = logfire.instrument_openai()

    app.state.redis = redis.from_url(str(settings.redis_url), decode_responses=True)

    try:
        async with AsyncExitStack() as stack:
            _ = await stack.enter_async_context(_cortex_app.lifespan(app))
            _ = await stack.enter_async_context(_utils_app.lifespan(app))
            yield
    finally:
        await app.state.redis.aclose()


app = FastAPI(lifespan=_lifespan)
app.add_middleware(OriginValidationMiddleware)
app.mount("/cortex", _cortex_app)
app.mount("/utils", _utils_app)
app.include_router(hooks_router, prefix="/hooks")


@app.get("/livez")
async def livez() -> dict[str, str]:
    """Process-up health check. Trivially true if FastAPI is responding."""
    return {"status": "ok"}
