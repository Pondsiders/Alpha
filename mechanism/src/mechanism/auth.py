"""Shared FastMCP token-verifier construction.

All three FastMCP servers (cortex, mechanism, utils) use the same bearer
token for tailnet-side access control. ``StaticTokenVerifier`` is the
FastMCP-native way to validate a fixed bearer token — adequate for our
single-user-per-deploy, tailnet-private deployment shape (per the FastMCP
docs, it should not be used in true production-grade deployments).

When ``MECHANISM_TOKEN`` isn't set in the environment, this returns
``None`` and the FastMCP servers run unauthenticated — appropriate for
local dev. Production must set the token.

``/livez`` (the `@custom_route` on the mechanism server) bypasses this
verifier by design — FastMCP's documented behavior, exactly what we want
for load-balancer and tailscale serve probes.
"""

from __future__ import annotations

from fastmcp.server.auth.providers.jwt import StaticTokenVerifier

from mechanism.settings import get_settings


def get_auth_verifier() -> StaticTokenVerifier | None:
    """Return the StaticTokenVerifier for the configured token, or None if unset."""
    token = get_settings().mechanism_token
    if token is None:
        return None
    return StaticTokenVerifier(tokens={token: {"client_id": "alpha"}})
