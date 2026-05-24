"""The `/livez` custom route — process-up health check on the mechanism server.

FastMCP's `@custom_route` decorator attaches a non-MCP HTTP endpoint to
the server's ASGI app. Custom routes bypass FastMCP's auth middleware by
design — exactly what we want for `/livez`, since load balancers and
tailscale serve probes shouldn't need a token.

When the mechanism server is mounted at ``/mechanism`` in the Starlette
parent, this route lives at ``/mechanism/livez``.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse

from mechanism.mechanism.server import mcp


@mcp.custom_route("/livez", methods=["GET"])
async def livez(_request: Request) -> JSONResponse:
    """Return 200 OK if the process is responding."""
    return JSONResponse({"status": "ok"})
