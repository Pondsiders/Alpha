"""Origin header validation middleware (DNS rebinding mitigation).

The MCP transports spec mandates that servers MUST validate the `Origin`
header on Streamable HTTP requests, to prevent DNS rebinding attacks
where a malicious page loaded in a browser can trick the browser into
making same-origin-looking requests to a localhost service.

The middleware applies uniformly to the Starlette parent — all three
mounted FastMCP sub-apps (`/cortex/mcp`, `/mechanism/mcp`, `/utils/mcp`)
and the unauthenticated `/mechanism/livez` custom route.

For mechanism's deployment, the legitimate clients (Claude Code's MCP
client and the Docker healthcheck using `urllib.request`) don't include
an `Origin` header on their requests. Browser-based clients legitimately
accessing the dev stack (MCP Inspector et al.) would carry their own
Origin and can be added to the allow-list when that workflow shows up.

Design constraint — uses `BaseHTTPMiddleware`, which buffers responses.
Starlette's `BaseHTTPMiddleware` materializes streamed responses into
memory before forwarding. FastMCP's Streamable HTTP transport uses SSE,
so this middleware would re-buffer any streaming response that flows
through it. In practice that's fine because the mechanism is purely
request/response shaped: every tool call returns a complete JSON
envelope, progress notifications don't reach the model (Claude Code
doesn't surface them), and Claude Code doesn't support MCP elicitation
or sampling — the two features that would require the bidirectional
channel to stay open mid-tool. If a future feature relies on
bidirectional streaming (e.g., if Claude Code ships elicitation or
sampling support and we want to use them), rewrite this as a pure
ASGI middleware first. See issue #34 for the analysis.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, override

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response

logger = logging.getLogger(__name__)

# Origins we consider legitimate. None = no Origin header sent;
# "" = Origin header sent with an empty value. Both are the
# expected shapes for non-browser clients in our deployment.
_ALLOWED_ORIGINS: frozenset[str | None] = frozenset({None, ""})


class OriginValidationMiddleware(BaseHTTPMiddleware):
    """Reject requests whose `Origin` header isn't in the allow-list."""

    @override
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Pass or 403 based on the Origin header."""
        origin = request.headers.get("origin")
        if origin not in _ALLOWED_ORIGINS:
            logger.warning(
                "Rejected request with unexpected Origin: %r (path=%s)",
                origin,
                request.url.path,
            )
            return JSONResponse(
                {"detail": "Origin not allowed"},
                status_code=403,
            )
        return await call_next(request)
