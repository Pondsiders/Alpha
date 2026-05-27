"""Pin the per-server alwaysLoad policy for the household tools.

Tool-search defers tool schemas out of context by default; the
``_meta['anthropic/alwaysLoad']=True`` opt-in tells Claude Code to keep
a tool's schema inline every turn. Different household servers want
opposite defaults:

- **cortex** and **utils**: model-callable tools used every turn
  (``store_memory``, ``search_memories``, ``fetch``, etc.). MUST always-load.
- **mechanism**: hook-shaped tools (``timestamp``, ``memories``,
  ``anamneses``, ``reflection``) that fire automatically via Claude
  Code's ``mcp_tool`` hook type. The model never calls them directly,
  so their schemas are pure context bloat. MUST NOT always-load.

Both directions are asserted: an accidentally-added meta on a mechanism
tool is as much a regression as an accidentally-dropped meta on a cortex
or utils tool.

The wire shape (``model_dump(by_alias=True)``) is what Claude Code reads,
so that's what the tests inspect — not the Python attribute on
``mcp.types.Tool``.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastmcp import Client, FastMCP

from mechanism.cortex import mcp as cortex_mcp
from mechanism.mechanism import mcp as mechanism_mcp
from mechanism.utils import mcp as utils_mcp


@pytest.mark.parametrize(
    ("server", "server_name"),
    [
        (cortex_mcp, "cortex"),
        (utils_mcp, "utils"),
    ],
)
async def test_model_callable_tools_declare_always_load(
    server: FastMCP,
    server_name: str,
) -> None:
    """Every cortex/utils tool must set ``_meta['anthropic/alwaysLoad']=True``."""
    async with Client(server) as client:
        tools = await client.list_tools()

    assert tools, f"{server_name}: list_tools() returned no tools — server not loaded?"

    missing: list[str] = []
    for tool in tools:
        wire: dict[str, Any] = tool.model_dump(by_alias=True)
        meta: dict[str, Any] = wire.get("_meta") or {}
        if meta.get("anthropic/alwaysLoad") is not True:
            missing.append(f"{tool.name} (got meta={meta!r})")

    assert not missing, (
        f"{server_name}: tools missing _meta['anthropic/alwaysLoad']=True:\n"
        + "\n".join(f"  - {m}" for m in missing)
    )


async def test_mechanism_tools_do_not_declare_always_load() -> None:
    """Mechanism tools are hook-shaped; the model never calls them. They must defer."""
    async with Client(mechanism_mcp) as client:
        tools = await client.list_tools()

    assert tools, "mechanism: list_tools() returned no tools — server not loaded?"

    unexpected: list[str] = []
    for tool in tools:
        wire: dict[str, Any] = tool.model_dump(by_alias=True)
        meta: dict[str, Any] = wire.get("_meta") or {}
        if meta.get("anthropic/alwaysLoad") is True:
            unexpected.append(f"{tool.name} (meta={meta!r})")

    assert not unexpected, (
        "mechanism: hook-shaped tools must not declare _meta['anthropic/alwaysLoad']=True"
        + " — they're invoked via Claude Code's mcp_tool hook type, never by the model directly."
        + " Offenders:\n"
        + "\n".join(f"  - {u}" for u in unexpected)
    )
