"""Pydantic models for Cortex MCP tool inputs and outputs.

These are the wire shapes the MCP server returns to clients. FastMCP
auto-generates JSON Schema from these so the LLM sees properly-shaped
tool descriptions and the inspector renders structured output.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DiaryEntry(BaseModel):
    """A single diary entry row from cortex.diary."""

    id: int = Field(description="Diary entry id.")
    content: str = Field(description="The diary entry text.")
    created_at: str = Field(description="When the entry was stored (PSO-8601, local time).")
    age: str = Field(description="How long ago the entry was stored.")


class DiaryResult(BaseModel):
    """The result of appending a diary entry."""

    id: int = Field(description="The id of the newly-stored entry.")
    created_at: str = Field(description="When the entry was stored (PSO-8601, local time).")


class SearchHit(BaseModel):
    """A single memory returned by the search tool."""

    id: int = Field(description="The memory id.")
    content: str = Field(description="The memory text.")
    created_at: str = Field(description="When the memory was stored (PSO-8601, local time).")
    age: str = Field(description="How long ago the memory was stored.")
    score: float = Field(
        description=(
            "Relevance score. For mode='semantic', cosine similarity in [0, 1] "
            "(higher is closer). For mode='index', raw ts_rank_cd (unbounded, "
            "monotonic within a result set, not comparable between result sets)."
        )
    )


class SearchMemoriesResult(BaseModel):
    """The result envelope from search_memories — echoes the call's mode and query."""

    mode: str = Field(description="The mode that produced these hits ('semantic' or 'index').")
    query: str = Field(description="The search text that produced these hits.")
    hits: list[SearchHit] = Field(description="Matching memories, ordered by descending score.")


class StoreResult(BaseModel):
    """The result of storing a memory."""

    id: int = Field(description="The id of the newly-stored memory.")
    created_at: str = Field(description="When the memory was stored (PSO-8601, local time).")


class Memory(BaseModel):
    """A single memory row from cortex.memories."""

    id: int = Field(description="The memory id.")
    content: str = Field(description="The memory text.")
    created_at: str = Field(description="When the memory was stored (PSO-8601, local time).")
    age: str = Field(description="How long ago the memory was stored.")
