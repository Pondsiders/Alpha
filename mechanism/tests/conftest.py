"""Pytest fixtures shared by all test modules."""

from __future__ import annotations

import os
import subprocess
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from openai.types import CreateEmbeddingResponse, Embedding
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice
from pydantic import ValidationError
from testcontainers.postgres import PostgresContainer  # pyright: ignore[reportMissingTypeStubs]
from testcontainers.redis import RedisContainer  # pyright: ignore[reportMissingTypeStubs]

from mechanism import db
from mechanism.redis_client import close_redis_client
from mechanism.settings import Settings

_SCHEMA_SQL_PATH = Path(__file__).parent / "fixtures" / "schema.sql"
_SEED_SQL_PATH = Path(__file__).parent / "fixtures" / "seed.sql"
_EMBEDDING_DIMENSIONS = 2560  # Qwen 3 Embedding 4B; see llm.format_query_for_embedding.

_postgres_container: PostgresContainer | None = None
_redis_container: RedisContainer | None = None
_stubbed_llm_creds: bool = False


def pytest_configure(config: pytest.Config) -> None:  # pyright: ignore[reportUnusedParameter]
    """Start ephemeral pgvector + redis containers; wire DATABASE_URL/REDIS_URL.

    Each pytest session starts its own containers on random host ports, so
    multiple sessions (e.g. parallel issue-fixer agents in separate worktrees)
    can run without colliding. The containers are torn down in
    pytest_unconfigure at session end.

    Also stubs Settings-required env vars when they're absent, so the test
    suite runs in a fresh checkout / worktree without a `.env` file.
    Detection is delegated to Settings itself: if `Settings()` raises
    `ValidationError`, required fields are missing — stub them all via
    `setdefault` (preserving any value the shell or the `just test` recipe
    already provided) and flip `_stubbed_llm_creds` so `_ci_block_llm_calls`
    blanket-mocks the OpenAI clients. `DATABASE_URL` and `REDIS_URL` get
    placeholder stubs unconditionally — Settings just needs them to be
    present-and-parseable here, and the testcontainer block below
    overwrites them with the real ephemeral URLs a few lines later.

    Runs before any test collection, so the env vars are set before any
    mechanism module is imported and before settings.get_settings() is cached.
    """
    global _postgres_container, _redis_container, _stubbed_llm_creds

    # Placeholders for fields the testcontainer block overwrites later.
    # Settings just needs valid URLs to construct.
    _ = os.environ.setdefault(
        "DATABASE_URL", "postgresql://placeholder:placeholder@localhost/placeholder"
    )
    _ = os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

    # Ask Settings whether real config is reachable. If validation fails,
    # required fields are missing — stub every required field via setdefault
    # (no-op when the value is already set) and flip the marker so the LLM
    # clients get blanket-mocked downstream.
    try:
        _ = Settings()  # pyright: ignore[reportCallIssue]
    except ValidationError:
        _stubbed_llm_creds = True
        _ = os.environ.setdefault("MECHANISM_TOKEN", "test-token-not-a-real-secret")
        _ = os.environ.setdefault("TIMEZONE", "America/Los_Angeles")
        _ = os.environ.setdefault("CHAT_API_KEY", "test-not-used")
        _ = os.environ.setdefault("CHAT_BASE_URL", "https://test.invalid/v1")
        _ = os.environ.setdefault("CHAT_MODEL", "test-chat-model")
        _ = os.environ.setdefault("EMBEDDING_API_KEY", "test-not-used")
        _ = os.environ.setdefault("EMBEDDING_BASE_URL", "https://test.invalid/v1")
        _ = os.environ.setdefault("EMBEDDING_MODEL", "test-embedding-model")

    _postgres_container = PostgresContainer(
        "pgvector/pgvector:pg17",
        username="postgres",
        password="postgres",
        dbname="postgres",
        driver=None,
    )
    _ = _postgres_container.start()

    _redis_container = RedisContainer("redis:8")
    _ = _redis_container.start()

    pg_host = _postgres_container.get_container_host_ip()
    pg_port = _postgres_container.get_exposed_port(5432)
    redis_host = _redis_container.get_container_host_ip()
    redis_port = _redis_container.get_exposed_port(6379)

    os.environ["DATABASE_URL"] = f"postgresql://postgres:postgres@{pg_host}:{pg_port}/postgres"
    os.environ["REDIS_URL"] = f"redis://{redis_host}:{redis_port}/0"

    # Load schema.sql via host psql. The schema is a pg_dump output containing
    # psql meta-commands (\restrict etc.) that psycopg can't execute directly.
    _ = subprocess.run(
        [
            "psql",
            "-h",
            pg_host,
            "-p",
            str(pg_port),
            "-U",
            "postgres",
            "-d",
            "postgres",
            "-v",
            "ON_ERROR_STOP=1",
            "-f",
            str(_SCHEMA_SQL_PATH),
        ],
        env={**os.environ, "PGPASSWORD": "postgres"},
        check=True,
        capture_output=True,
    )


def pytest_unconfigure(config: pytest.Config) -> None:  # pyright: ignore[reportUnusedParameter]
    """Stop the testcontainers at session end."""
    global _postgres_container, _redis_container
    if _postgres_container is not None:
        _postgres_container.stop()
        _postgres_container = None
    if _redis_container is not None:
        _redis_container.stop()
        _redis_container = None


@pytest.fixture(autouse=True)
async def _reset_state_between_tests() -> AsyncGenerator[None]:  # pyright: ignore[reportUnusedFunction]
    """TRUNCATE the test data tables before each test; reset async singletons after.

    Three failure modes this addresses:

    1. **DB pollution between tests.** Without isolation, a row written by
       test A is visible to test B (e.g. `test_store_memory` leaves a real-
       embedding row that the memories tool test then finds by cosine
       similarity). TRUNCATE-before-each-test gives every test a clean
       cortex.* baseline; tests that write their own rows still work
       because they assert by the id they just got back.

    2. **asyncpg pool poisoning across event loops.** Pools are bound to
       the event loop they were created in. Each pytest-asyncio test runs
       in a fresh event loop, so a singleton pool created in one test
       poisons subsequent tests with `cannot perform operation: another
       operation is in progress`. Closing the pool after each test means
       the next test starts fresh.

    3. **Redis client singleton poisoning across event loops.** Same shape
       as the asyncpg case: `get_redis_client()` returns a process-singleton
       async Redis client whose underlying connection is bound to whichever
       event loop opened it. Closing the singleton after each test means
       the next test's first `get_redis_client()` call gets a fresh client
       bound to the new loop.
    """
    from mechanism.db import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        _ = await conn.execute("TRUNCATE cortex.memories, cortex.diary RESTART IDENTITY CASCADE")

    yield

    if db._pool is not None:  # pyright: ignore[reportPrivateUsage]
        await db._pool.close()  # pyright: ignore[reportPrivateUsage]
        db._pool = None  # pyright: ignore[reportPrivateUsage]

    await close_redis_client()


def _zero_embedding_response(n_inputs: int) -> CreateEmbeddingResponse:
    """Build a CreateEmbeddingResponse with `n_inputs` zero vectors."""
    return CreateEmbeddingResponse(
        object="list",
        model="fake-embed-model",
        usage={"prompt_tokens": 0, "total_tokens": 0},  # pyright: ignore[reportArgumentType]
        data=[
            Embedding(index=i, object="embedding", embedding=[0.0] * _EMBEDDING_DIMENSIONS)
            for i in range(n_inputs)
        ],
    )


def _empty_chat_response() -> ChatCompletion:
    """Build a ChatCompletion with an empty JSON-array content."""
    return ChatCompletion(
        id="fake-chatcmpl",
        object="chat.completion",
        created=0,
        model="fake-chat-model",
        choices=[
            Choice(
                index=0,
                finish_reason="stop",
                message=ChatCompletionMessage(role="assistant", content="[]"),
            )
        ],
    )


@pytest.fixture(autouse=True)
def _ci_block_llm_calls(monkeypatch: pytest.MonkeyPatch) -> None:  # pyright: ignore[reportUnusedFunction]
    """Blanket-mock the LLM clients whenever real Bifrost credentials are absent.

    Local dev with a populated `.env` (or shell-exported Bifrost creds):
    no-op. Tests that need real Bifrost (store_memory) get it; tests that
    need a tracking mock opt into `mock_llm`. The clients hit the
    configured Bifrost gateway like they would in production.

    CI or fresh checkout (no `.env`, no exported creds — see
    `pytest_configure`'s `_stubbed_llm_creds` path): blanket monkeypatches
    that return valid empty shapes. Tests that opt into `mock_llm`
    re-monkeypatch with tracking versions on top (last setattr wins, LIFO
    undo on teardown). The blanket prevents store_memory, anamneses,
    memories, etc. from reaching for a Bifrost that isn't there.
    """
    if not os.environ.get("MECHANISM_CI") and not _stubbed_llm_creds:
        return

    from mechanism import llm

    chat_client = llm.get_chat_client()
    embed_client = llm.get_embedding_client()

    async def blanket_chat(**_kwargs: Any) -> ChatCompletion:
        return _empty_chat_response()

    async def blanket_embed(**kwargs: Any) -> CreateEmbeddingResponse:
        raw_input = kwargs.get("input")
        n_inputs = (
            len(raw_input) if isinstance(raw_input, list) else 1  # pyright: ignore[reportUnknownArgumentType]
        )
        return _zero_embedding_response(n_inputs)

    monkeypatch.setattr(chat_client.chat.completions, "create", blanket_chat)
    monkeypatch.setattr(embed_client.embeddings, "create", blanket_embed)


@pytest.fixture
async def seeded(_reset_state_between_tests: None) -> None:
    """Load `fixtures/seed.sql` on top of the post-TRUNCATE empty baseline.

    Depends on `_reset_state_between_tests` (the autouse TRUNCATE) so the seed
    lands into a clean cortex.memories / cortex.diary. Tests that need seed
    data declare `seeded` as a parameter; tests that don't get an empty DB
    (so e.g. the memories tool no-op assertion stays meaningful).

    Per-test reseed is intentional — seed.sql is ~200 KB of pre-computed
    Qwen embeddings, so each test starts from an identical fixture state.
    Regenerate via `just seed-generate`.
    """
    from mechanism.db import get_pool

    seed_sql = _SEED_SQL_PATH.read_text(encoding="utf-8")
    pool = await get_pool()
    async with pool.acquire() as conn:
        _ = await conn.execute(seed_sql)


@pytest.fixture
def mock_llm(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[dict[str, Any]]]:
    """Monkeypatch the LLM clients' `.create()` methods with deterministic stubs.

    Constructs the real chat and embedding clients via the module-level
    factories (lazy singletons), then replaces only their network-calling
    `create` methods. The rest of the code path — settings load, client
    construction, the format-for-embedding step, response parsing — all
    still runs against the real surfaces. Only the wire is faked.

    Both call sites (the `memories` and `anamneses` MCP tools) currently
    expect the same response shape: a JSON-encoded array of strings in
    `choices[0].message.content`. Until that changes, one fixed canned
    response covers both. Per Jeffery's principle: pre-engineering for
    hypothetical future shapes is the same trap as defensive tests for
    bugs we'd never write.

    Returns a dict with `chat_calls` and `embed_calls` lists so tests can
    assert on what got sent to the wire (the right prompt? the right
    number of embedded queries?).
    """
    from mechanism import llm

    chat_client = llm.get_chat_client()
    embed_client = llm.get_embedding_client()

    chat_calls: list[dict[str, Any]] = []
    embed_calls: list[dict[str, Any]] = []

    async def fake_chat_create(**kwargs: Any) -> ChatCompletion:
        chat_calls.append(kwargs)
        return ChatCompletion(
            id="fake-chatcmpl",
            object="chat.completion",
            created=0,
            model="fake-chat-model",
            choices=[
                Choice(
                    index=0,
                    finish_reason="stop",
                    message=ChatCompletionMessage(
                        role="assistant",
                        content='["test query alpha", "test query beta"]',
                    ),
                )
            ],
        )

    async def fake_embed_create(**kwargs: Any) -> CreateEmbeddingResponse:
        embed_calls.append(kwargs)
        raw_input = kwargs.get("input")
        n_inputs = (
            len(raw_input) if isinstance(raw_input, list) else 1  # pyright: ignore[reportUnknownArgumentType]
        )
        return CreateEmbeddingResponse(
            object="list",
            model="fake-embed-model",
            usage={"prompt_tokens": 0, "total_tokens": 0},  # pyright: ignore[reportArgumentType]
            data=[
                Embedding(index=i, object="embedding", embedding=[0.0] * _EMBEDDING_DIMENSIONS)
                for i in range(n_inputs)
            ],
        )

    monkeypatch.setattr(chat_client.chat.completions, "create", fake_chat_create)
    monkeypatch.setattr(embed_client.embeddings, "create", fake_embed_create)

    return {"chat_calls": chat_calls, "embed_calls": embed_calls}


@pytest.fixture
async def http_client() -> AsyncGenerator[AsyncClient]:
    """An httpx AsyncClient for the Starlette parent app.

    Tests HTTP-level surfaces — currently just `/mechanism/livez`, the
    `@mcp.custom_route` health check that bypasses FastMCP auth. The MCP
    tools themselves get tested via the FastMCP in-memory client, not
    through this fixture.

    Bypasses the full app lifespan (Logfire configuration, mounted MCP
    sub-app startup). Redis is reached by handlers via `get_redis_client()`,
    the process-singleton in `mechanism.redis_client`; the autouse
    `_reset_state_between_tests` fixture closes the singleton between tests
    so each test gets a client on its own event loop.
    """
    from mechanism.app import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
