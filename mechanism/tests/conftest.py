"""Pytest fixtures shared by all test modules."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import pytest
import redis.asyncio as redis
from httpx import ASGITransport, AsyncClient
from openai.types import CreateEmbeddingResponse, Embedding
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice

from mechanism import db


def pytest_configure(config: pytest.Config) -> None:  # pyright: ignore[reportUnusedParameter]
    """Refuse to run unless the test environment is explicitly configured.

    Loud safety net against the failure mode that produced #10: pytest
    reaching for a `DATABASE_URL` that happens to be set to production.
    Production code only ever reads `DATABASE_URL` / `REDIS_URL`; this hook
    rewrites them from the `TEST_*` values at session start, so
    `get_settings()` (lru_cached) picks up the test values on first call.

    The TEST_* vars must be set AND must differ from the production URLs.
    A missing or matching value causes pytest to exit immediately.
    """
    test_db = os.environ.get("TEST_DATABASE_URL")
    test_redis = os.environ.get("TEST_REDIS_URL")
    if not test_db or not test_redis:
        pytest.exit(
            "TEST_DATABASE_URL and TEST_REDIS_URL are required for the test"
            + " suite. Run `just test-up` and set both vars (see the `test`"
            + " recipe in the justfile for the canonical values).",
            returncode=2,
        )
    if test_db == os.environ.get("DATABASE_URL"):
        pytest.exit(
            "TEST_DATABASE_URL equals DATABASE_URL."
            + " Refusing to run tests against the production database.",
            returncode=2,
        )
    if test_redis == os.environ.get("REDIS_URL"):
        pytest.exit(
            "TEST_REDIS_URL equals REDIS_URL."
            + " Refusing to run tests against the production Redis.",
            returncode=2,
        )
    os.environ["DATABASE_URL"] = test_db
    os.environ["REDIS_URL"] = test_redis


@pytest.fixture(autouse=True)
async def _clean_db_and_reset_pool() -> AsyncGenerator[None]:  # pyright: ignore[reportUnusedFunction]
    """TRUNCATE the test data tables before each test; reset the asyncpg pool after.

    Two failure modes this addresses:

    1. **DB pollution between tests.** Without isolation, a row written by
       test A is visible to test B (e.g. `test_store_memory` leaves a real-
       embedding row that the memories-hook test then finds by cosine
       similarity). TRUNCATE-before-each-test gives every test a clean
       cortex.* baseline; tests that write their own rows still work
       because they assert by the id they just got back.

    2. **asyncpg pool poisoning across event loops.** Pools are bound to
       the event loop they were created in. Each pytest-asyncio test runs
       in a fresh event loop, so a singleton pool created in one test
       poisons subsequent tests with `cannot perform operation: another
       operation is in progress`. Closing the pool after each test means
       the next test starts fresh.
    """
    from mechanism.db import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        _ = await conn.execute("TRUNCATE cortex.memories, cortex.diary RESTART IDENTITY CASCADE")

    yield

    if db._pool is not None:  # pyright: ignore[reportPrivateUsage]
        await db._pool.close()  # pyright: ignore[reportPrivateUsage]
        db._pool = None  # pyright: ignore[reportPrivateUsage]


_EMBEDDING_DIMENSIONS = 2560  # Qwen 3 Embedding 4B; see llm.format_query_for_embedding.

_SEED_SQL_PATH = Path(__file__).parent / "fixtures" / "seed.sql"


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
    """In CI, blanket-mock the LLM clients so no test makes a real network call.

    Local dev: no-op. Tests that need real Bifrost (store_memory) get it;
    tests that need a tracking mock opt into `mock_llm`. The clients hit
    the configured Bifrost gateway like they would in production.

    CI: blanket monkeypatches that return valid empty shapes. Tests that
    opt into `mock_llm` re-monkeypatch with tracking versions on top
    (last setattr wins, LIFO undo on teardown). The blanket prevents
    store_memory, anamneses, memories, etc. from reaching for a Bifrost
    that isn't there.
    """
    if not os.environ.get("MECHANISM_CI"):
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
async def seeded(_clean_db_and_reset_pool: None) -> None:
    """Load `fixtures/seed.sql` on top of the post-TRUNCATE empty baseline.

    Depends on `_clean_db_and_reset_pool` (the autouse TRUNCATE) so the seed
    lands into a clean cortex.memories / cortex.diary. Tests that need seed
    data declare `seeded` as a parameter; tests that don't get an empty DB
    (so e.g. the memories-hook no-op assertion stays meaningful).

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

    Both call sites (`/hooks/memories` and `/hooks/anamneses`) currently
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
                Embedding(
                    index=i, object="embedding", embedding=[0.0] * _EMBEDDING_DIMENSIONS
                )
                for i in range(n_inputs)
            ],
        )

    monkeypatch.setattr(chat_client.chat.completions, "create", fake_chat_create)
    monkeypatch.setattr(embed_client.embeddings, "create", fake_embed_create)

    return {"chat_calls": chat_calls, "embed_calls": embed_calls}


@pytest.fixture
async def hooks_client() -> AsyncGenerator[AsyncClient]:
    """An httpx AsyncClient for the FastAPI app, with Redis wired in directly.

    Bypasses the full FastAPI lifespan (which handles production-only concerns
    like Logfire configuration and the mounted MCP sub-apps' startup); hook
    handlers only need `request.app.state.redis`, so we attach that and skip
    the rest. Lifespan is a production-only concern; tests inject what each
    handler actually requires.
    """
    from mechanism.app import app

    app.state.redis = redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client
    finally:
        await app.state.redis.aclose()
