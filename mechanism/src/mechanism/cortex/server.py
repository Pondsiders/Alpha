"""The FastMCP server instance for Cortex.

Tool modules import `mcp` from here and register themselves via the
`@mcp.tool` decorator. The package `__init__` imports the tool modules
for their side effects, so that mounting this server's ASGI app picks
up the full tool surface.
"""

from __future__ import annotations

from importlib.metadata import version
from pathlib import Path

from fastmcp import FastMCP

from mechanism.auth import get_auth_verifier

_INSTRUCTIONS = (Path(__file__).parent / "instructions.md").read_text(encoding="utf-8")

mcp: FastMCP = FastMCP(
    "cortex",
    instructions=_INSTRUCTIONS,
    version=version("mechanism"),
    auth=get_auth_verifier(),
)
