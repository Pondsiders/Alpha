"""The `get_schema` tool — return the DDL shape of the cortex schema."""

from __future__ import annotations

from mcp.types import ToolAnnotations

from alpha_server.cortex.server import mcp
from alpha_server.db import get_pool

_SCHEMA = "cortex"

_QUERY = """
SELECT table_name, column_name, data_type, udt_name, is_nullable, character_maximum_length
  FROM information_schema.columns
 WHERE table_schema = $1
 ORDER BY table_name, ordinal_position
"""


def _format_type(data_type: str, udt_name: str, char_max_length: int | None) -> str:
    """Render a Postgres column type the way a DDL writer would.

    `information_schema` reports user-defined types (vector, halfvec, geometry,
    etc.) as `USER-DEFINED` with the real name in `udt_name`. Variable-length
    text types use `character_maximum_length`. Built-in scalar types come back
    with reasonable defaults already.
    """
    if data_type == "USER-DEFINED":
        return udt_name
    if data_type == "ARRAY":
        # Strip leading underscore: _int4 -> int4[]
        base = udt_name.lstrip("_")
        return f"{base}[]"
    if char_max_length is not None and data_type in {"character varying", "character"}:
        short = "varchar" if data_type == "character varying" else "char"
        return f"{short}({char_max_length})"
    return data_type


@mcp.tool(
    description="Return the schema of the cortex database — tables, columns, and types.",
    annotations=ToolAnnotations(
        title="Get schema",
        readOnlyHint=True,
        openWorldHint=False,
    ),
)
async def get_schema() -> str:
    """Return a compact DDL-shaped description of the cortex schema.

    Renders each table as a CREATE TABLE-style block. Suitable as
    context for writing `execute_query` calls — the column names and
    types are visible at a glance.

    Returns:
        A multi-line string. One block per table, blank lines between.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(_QUERY, _SCHEMA)

    tables: dict[str, list[str]] = {}
    for row in rows:
        type_str = _format_type(row["data_type"], row["udt_name"], row["character_maximum_length"])
        nullable = "" if row["is_nullable"] == "YES" else " NOT NULL"
        line = f"    {row['column_name']} {type_str}{nullable}"
        tables.setdefault(row["table_name"], []).append(line)

    blocks = [
        f"{_SCHEMA}.{table_name}(\n" + ",\n".join(lines) + "\n)"
        for table_name, lines in tables.items()
    ]
    return "\n\n".join(blocks)
