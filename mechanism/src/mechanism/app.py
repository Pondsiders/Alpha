"""ASGI application factory.

Starlette parent composing three FastMCP servers (cortex, mechanism,
utils) over Streamable HTTP.

``/livez`` lives on the mechanism FastMCP server via ``@custom_route``
and is reachable at ``/mechanism/livez``. Custom routes bypass FastMCP
auth by design — what we want for load-balancer probes.

Run with:
    uv run uvicorn mechanism.app:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

from contextlib import AsyncExitStack, asynccontextmanager
from typing import TYPE_CHECKING

import logfire
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.routing import Mount

from mechanism.cortex import mcp as cortex_mcp
from mechanism.db import close_pool
from mechanism.llm import close_llm_clients
from mechanism.mechanism import mcp as mechanism_mcp
from mechanism.origin_validation import OriginValidationMiddleware
from mechanism.redis_client import close_redis_client
from mechanism.settings import get_settings
from mechanism.utils import mcp as utils_mcp

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


_cortex_app = cortex_mcp.http_app(path="/mcp")
_mechanism_app = mechanism_mcp.http_app(path="/mcp")
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
async def _lifespan(app: Starlette) -> AsyncGenerator[None]:
    """Configure observability and compose the mounted FastMCP lifespans.

    The three FastMCP session managers need to start before requests
    arrive at the mounted sub-apps; otherwise mounted tool calls hang.
    ``AsyncExitStack`` composes each sub-app's lifespan so adding another
    mounted MCP server is a single ``enter_async_context`` line.

    LLM clients, the database pool, and the Redis client are lazy
    module-level singletons (``llm.py``, ``db.py``, ``redis_client.py``);
    each gets an explicit teardown on shutdown so warm reloads and test
    boundaries don't leak FDs to Postgres, Redis, or the Bifrost gateway.
    """
    settings = get_settings()

    _ = logfire.configure(
        send_to_logfire="if-token-present",
        token=settings.logfire_token,
        service_name=settings.otel_service_name,
        scrubbing=logfire.ScrubbingOptions(callback=_scrubbing_callback),
    )
    logfire.instrument_mcp()
    logfire.instrument_httpx()
    logfire.instrument_asyncpg()
    _ = logfire.instrument_openai()

    try:
        async with AsyncExitStack() as stack:
            _ = await stack.enter_async_context(_cortex_app.lifespan(app))
            _ = await stack.enter_async_context(_mechanism_app.lifespan(app))
            _ = await stack.enter_async_context(_utils_app.lifespan(app))
            yield
    finally:
        await close_redis_client()
        await close_pool()
        await close_llm_clients()


app = Starlette(
    lifespan=_lifespan,
    middleware=[Middleware(OriginValidationMiddleware)],
    routes=[
        Mount("/cortex", _cortex_app),
        Mount("/mechanism", _mechanism_app),
        Mount("/utils", _utils_app),
    ],
)
