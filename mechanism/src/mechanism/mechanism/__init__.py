"""The `mechanism` MCP server — hook tools invokable over MCP transport.

Each tool here mirrors the behavior of a `/hooks/*` HTTP endpoint, but is
exposed as an MCP tool so it can be invoked via the `mcp_tool` hook type
from harnesses that can't reach private IPs over HTTP (e.g. Claude Code
running on a remote machine across a tailnet).

The `mcp` instance lives in `server`; tool modules are imported here for
their side effects (each module's `@mcp.tool` decorator registers its
tool against the shared instance). Mounting `mcp.http_app(...)` inside
the FastAPI app picks up the full tool surface.
"""

from mechanism.mechanism import anamneses, livez, memories, reflection, timestamp
from mechanism.mechanism.server import mcp

# Side-effect imports — silence the unused-import warnings.
_ = (anamneses, livez, memories, reflection, timestamp)

__all__ = ["mcp"]
