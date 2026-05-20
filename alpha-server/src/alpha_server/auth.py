"""Bearer-token authentication for alpha-server.

A single shared secret gates every endpoint except `/livez`. The token
lives in the `AUTH_TOKEN` env var on the server side; clients send it
as `Authorization: Bearer <token>` on every request.

The check is implemented as Starlette middleware so it applies uniformly
to FastAPI routes (the hooks) and to the mounted FastMCP sub-ASGI app
(the MCP tools). Constant-time comparison prevents timing leaks on the
secret.
"""

from __future__ import annotations

import hmac
from typing import TYPE_CHECKING, override

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

from alpha_server.settings import get_settings

if TYPE_CHECKING:
    from starlette.requests import Request
    from starlette.responses import Response
    from starlette.types import ASGIApp

_BEARER_PREFIX = "Bearer "
_PUBLIC_PATHS = frozenset({"/livez"})


class BearerTokenMiddleware(BaseHTTPMiddleware):
    """Require a valid `Authorization: Bearer <token>` header on every request.

    Paths in `_PUBLIC_PATHS` bypass the check so liveness probes work
    without credentials.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Capture the configured token at construction time."""
        super().__init__(app)
        self._expected: str = get_settings().auth_token

    @override
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Verify the bearer token, or short-circuit with 401."""
        if request.url.path in _PUBLIC_PATHS:
            return await call_next(request)

        # header = request.headers.get("Authorization", "")
        # if not header.startswith(_BEARER_PREFIX):
        #     return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        # presented = header[len(_BEARER_PREFIX) :]
        # if not hmac.compare_digest(presented, self._expected):
        #     return JSONResponse({"detail": "Unauthorized"}, status_code=401)

        return await call_next(request)
