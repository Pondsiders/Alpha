"""The FastMCP server instance for the `mechanism` hook-tool surface.

Tool modules import `mcp` from here and register themselves via the
`@mcp.tool` decorator. The package `__init__` imports the tool modules
for their side effects, so that mounting this server's ASGI app picks
up the full tool surface.
"""

from __future__ import annotations

from importlib.metadata import version

from fastmcp import FastMCP

from mechanism.auth import get_auth_verifier

mcp: FastMCP = FastMCP(
    "mechanism",
    version=version("mechanism"),
    auth=get_auth_verifier(),
)
