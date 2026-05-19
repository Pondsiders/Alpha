"""Cortex MCP server — stdio mounting via `mcp`, tools registered by side effect.

The `mcp` instance lives in `server`; tool modules are imported here for
their side effects (each module's `@mcp.tool` decorator registers its tool
against the shared instance). Mounting `mcp.http_app(...)` inside the
FastAPI app picks up the full tool surface.
"""

from alpha_server.cortex import (
    add_to_diary,
    read_from_diary,
    recent_memories,
    search_memories,
    store_memory,
)
from alpha_server.cortex.server import mcp

# Side-effect imports — silence the unused-import warnings.
_ = (add_to_diary, read_from_diary, recent_memories, search_memories, store_memory)

__all__ = ["mcp"]
