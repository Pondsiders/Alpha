"""Process-singleton LLM clients and embedding-input formatting.

Lazy module-level singletons mirror the shape of `db.py`'s pool: the first
call to a `get_*_client()` constructs the client from Settings; subsequent
calls return the same instance. Both hooks and MCP tools share the same
clients, no lifespan handoff required.

`format_query_for_embedding` lives here too because each embedding model
has its own input-shape convention; centralizing it makes the model
fungible (alongside re-embedding the corpus).
"""

from __future__ import annotations

from openai import AsyncOpenAI

from mechanism.settings import get_settings

_chat_client: AsyncOpenAI | None = None
_embedding_client: AsyncOpenAI | None = None

_EMBEDDING_TASK = "Given a search query, retrieve relevant passages that are similar to the query"


def get_chat_client() -> AsyncOpenAI:
    """Return the process-singleton chat client, creating it on first call."""
    global _chat_client
    if _chat_client is None:
        settings = get_settings()
        _chat_client = AsyncOpenAI(
            base_url=str(settings.chat_base_url),
            api_key=settings.chat_api_key,
        )
    return _chat_client


def get_chat_model() -> str:
    """Return the configured chat model name."""
    return get_settings().chat_model


def get_embedding_client() -> AsyncOpenAI:
    """Return the process-singleton embedding client, creating it on first call."""
    global _embedding_client
    if _embedding_client is None:
        settings = get_settings()
        _embedding_client = AsyncOpenAI(
            base_url=str(settings.embedding_base_url),
            api_key=settings.embedding_api_key,
        )
    return _embedding_client


def get_embedding_model() -> str:
    """Return the configured embedding model name."""
    return get_settings().embedding_model


async def close_llm_clients() -> None:
    """Close the singleton chat and embedding clients if they're open.

    Called from the app lifespan. Closes the underlying httpx clients
    held by AsyncOpenAI so warm reloads and test boundaries don't leak
    connections to the Bifrost gateway.
    """
    global _chat_client, _embedding_client
    if _chat_client is not None:
        await _chat_client.close()
        _chat_client = None
    if _embedding_client is not None:
        await _embedding_client.close()
        _embedding_client = None


def format_query_for_embedding(query: str) -> str:
    r"""Format a query string for Qwen 3 Embedding 4B's input.

    This function is coupled to a specific embedding model:
    Qwen 3 Embedding 4B (https://huggingface.co/Qwen/Qwen3-Embedding-4B).
    Its model card prescribes the `Instruct: <task>\nQuery:<text>` shape
    for query inputs (documents are embedded without the prefix).

    If we swap embedding models, this function MUST be revisited
    (alongside re-embedding cortex.memories with the new model). The
    output here is wrong for any other embedding model.

    Args:
        query: The raw user query string.

    Returns:
        The query reshaped for Qwen 3 Embedding 4B's input.
    """
    return f"Instruct: {_EMBEDDING_TASK}\nQuery:{query}"
