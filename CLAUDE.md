# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Special rule for this repository specifically

Don't merge any code to main until Jeffery has had a chance to review and approve it.

## Git conventions

Commit messages **and PR titles** follow [Conventional Commits](https://www.conventionalcommits.org/). This isn't cosmetic: we squash-merge, and python-semantic-release (PSR) parses the resulting commit subject to compute the version bump and changelog. Under squash-merge the **PR title becomes that subject**, so a malformed title means a wrong or missing release. The `pr-title` workflow lints every PR title against the vocabulary below (a required check); its `types` list and PSR's `allowed_tags` are two copies of this one table and must stay in sync.

Format is `type(optional-scope): subject` — e.g. `feat(cortex): add semantic dedup`.

| type | bump | changelog section |
|------|------|-------------------|
| `feat` | minor | Features |
| `fix` | patch | Bug Fixes |
| `perf` | patch | Performance Improvements |
| `build` | none | Build System |
| `chore` | none | Chores |
| `ci` | none | Continuous Integration |
| `docs` | none | Documentation |
| `style` | none | Code Style |
| `refactor` | none | Refactoring |
| `test` | none | Testing |

Only `feat`/`fix`/`perf` move the version. **Breaking changes** bump major: append `!` after the type/scope (`feat!:`, `feat(api)!:`) or add a `BREAKING CHANGE:` paragraph to the commit body.

Releases are **manual**: pushing to `main` only runs tests; a maintainer runs the `ship` workflow (`workflow_dispatch`) to cut a version. Each PR is one changelog line driven by its title — the squash body is blank by default, so a 100-commit branch is still one entry. To itemize one PR into several entries, hand-write conventional bullets into the squash commit body at merge time; PSR parses each as its own entry, highest bump wins:

```
fix: clear the backlog (#123)

* fix: thing one
* feat: thing two
```

## Repository layout

This is a small monorepo. The only source tree is `mechanism/` (a Python package); everything at the repo root is infra glue: a `Dockerfile` and `compose.yml` for production, `compose-dev.yml` for the local dev stack, a `justfile`, a `.env` shared by dev/prod, and GitHub Actions workflows under `.github/`.

Per-deploy identity (compose project name, tailscale hostname) lives in a `compose.override.yml` next to `compose.yml` — gitignored, copied from `compose.override.yml.example` on each deploy box and edited for that deploy's name. Docker Compose auto-merges the override; the source tree stays fork-identical, so divergence lives in deploy overrides, not in code.

## Commands

All `just` recipes run from the repo root; all `uv` commands run from `mechanism/`.

Dev environment (Postgres+pgvector, Redis, and `mechanism` with uvicorn on `127.0.0.1:8001`). Compose project name is `mechanism-dev`. DB ports bind to `127.0.0.1` (Postgres on `5432`, Redis on `6379`) so they're not exposed beyond the loopback interface. Two dev stacks on the same host will collide on these ports. (Tests don't use this stack — they spin up their own ephemeral containers; see below.)

```
just dev-up                # start
just dev-down              # stop (data preserved)
just dev-init <dump.sql>   # WIPE volumes and pg_restore from a dump
just dev-logs [-f] [svc]   # tail container logs
```

Tests bring up their own ephemeral pgvector + Redis containers via Testcontainers (random host ports, so multiple sessions — e.g. parallel agents — never collide), so the dev stack can keep running alongside.

```
just test                  # run pytest (Testcontainers spin up + tear down per session)
just seed-generate         # re-materialize seed.sql from seed.sql.template (embeddings via Bifrost)
```

Server, lint, typecheck (from `mechanism/`):

```
uv sync
uv run uvicorn mechanism.app:app --host 127.0.0.1 --port 8000
uv run pytest                                    # prefer `just test` — it sets the test env vars
uv run ruff check
uv run ruff format
uv run basedpyright
```

`pytest` is `asyncio_mode=auto`. `conftest.py` spins up ephemeral pgvector + Redis containers via Testcontainers at session start and loads `tests/fixtures/schema.sql` into them, so tests never point at a live dev or prod database. The LLM is mocked via the `mock_llm` fixture (monkeypatches `.create()` on the live OpenAI clients); when no Bifrost credentials are present (CI, or a fresh checkout), a blanket monkeypatch returns valid empty shapes — `MECHANISM_CI=1` forces that path. Per-test `TRUNCATE` keeps DB state isolated. CI (`test.yml`) runs the same suite with `MECHANISM_CI=1`; the Postgres/Redis come from Testcontainers, not GitHub `services:` blocks.

Pre-commit is installed (`uv run pre-commit install` once per clone). The hooks run ruff check, ruff format, and basedpyright on commit. Don't bypass with `--no-verify` — fix the hook config if a hook is broken, fix the underlying issue if it isn't.

## Architecture

`mechanism.app:app` is a **Starlette parent** composing three FastMCP servers over Streamable HTTP. Mounts:

- **`/cortex/mcp`** — Cortex memory and diary tools (`store_memory`, `search_memories`, `recent_memories`, `get_memory`, `read_from_diary`, `add_to_diary`).
- **`/mechanism/mcp`** — hook-shaped MCP tools (`timestamp`, `memories`, `anamneses`, `reflection`). Invokable via Claude Code's `mcp_tool` hook type, which is what makes remote-keyboard CC sessions work over a tailnet.
- **`/utils/mcp`** — utility tools (e.g. `fetch`).
- **`/mechanism/livez`** — unauthenticated health check, attached to the mechanism FastMCP server via `@mcp.custom_route` (custom routes bypass FastMCP auth by design — exactly what we want for load-balancer and `tailscale serve` probes).

The lifespan composes each mounted FastMCP server's session manager via `AsyncExitStack` so adding another mounted server is one `enter_async_context` line. Skipping the hand-off causes mounted tool calls to hang.

### Auth

`auth.py` builds a `StaticTokenVerifier` (FastMCP-native bearer-token validator) shared by all three FastMCP servers. `MECHANISM_TOKEN` is **required** — Settings has no default, so startup fails loudly if it's unset rather than silently serving every tool unauthenticated to anything on the tailnet. Local dev sets it in `.env`; production sets it via CC's `settings.local.json` `env` block (so the same value reaches both the server and the CC clients sending the bearer header).

`/mechanism/livez` bypasses the verifier by design; it's a custom route on the mechanism server.

### Side-effect registration pattern

Three registries (one per FastMCP server) use the same trick: a shared registry object is created in one module, and feature modules register against it via decorators at import time. Importing the feature module **is** what wires it up.

- **`cortex/server.py`** creates the `mcp: FastMCP` instance; each tool module decorates a function with `@mcp.tool`. `cortex/__init__.py` does side-effect imports of every tool module. Tool result shapes live in `cortex/models.py`; the server's tool-surface prose lives in `cortex/instructions.md` (read at startup).
- **`mechanism/mechanism/server.py`** creates the `mcp` instance for the mechanism tool surface; `mechanism/mechanism/__init__.py` does the side-effect imports (`memories`, `anamneses`, `reflection`, `timestamp`, `livez`). System-prompt prose lives next to each tool as `<tool>_system_prompt.md`.
- **`utils/server.py`** creates the `mcp` instance for utility tools; `utils/__init__.py` does the side-effect imports.

When adding a tool, follow this pattern: write the module, then add it to the side-effect import in the corresponding `__init__.py`. Failing to add the import means the surface silently won't appear.

### Long-lived clients

Three process-singleton clients, all lazy module-level, all shared by the MCP tools:

- **`llm.py`** — `get_chat_client()` / `get_chat_model()` / `get_embedding_client()` / `get_embedding_model()`. Each constructs the OpenAI-protocol client (against the Bifrost gateway) on first call and returns the same instance thereafter. `llm.py` also owns `format_query_for_embedding()` — the Qwen 3 Embedding 4B input shape lives there because swapping the embedding model means revisiting both this prefix and re-embedding `cortex.memories`.
- **`db.py`** — `get_pool()` returns the process-singleton `asyncpg.Pool`.
- **`redis_client.py`** — `get_redis_client()` returns the process-singleton async Redis client. Closed explicitly on app shutdown via `close_redis_client()` in the lifespan teardown. MCP-tool handlers have no request scope, so the singleton pattern is what's available.

Three Redis key families share the database: `seen:<session_id>` (memories recall dedupe), `last-msg:<session_id>` (timestamp tool), `reflection:turn:<session_id>` (reflection turn counter, fires every third turn).

### Database

`db.py` holds the process-singleton `asyncpg.Pool`. Two non-obvious things:

- pgvector is registered against the `extensions` schema and the connection startup `search_path` is `public, extensions` (passed via `server_settings`, not `SET` — `SET` gets wiped on connection reset between borrows). Application tables are still schema-qualified (`cortex.memories`, `cortex.diary`).
- The dev compose stack uses `pgvector/pgvector:pg17`; in production pgvector lives in the `extensions` schema. The search-path setup tolerates either layout — a fork whose DB has pgvector in `public` will still resolve operators.

### Time

`clock.py` is the single canonical home for date/time work — other modules **do not import `datetime`, `time`, or `pendulum` directly**. ISO-8601 is the project's house format (`"Sun May 17 2026, 10:23 AM"`); "day" boundaries run from 6 AM local to 6 AM local (see `start_of_day`). The local timezone is configured via the `TIMEZONE` env var.

### Settings

`settings.py` uses Pydantic Settings; `get_settings()` is `lru_cache`'d. The `.env` file is resolved relative to `settings.py` (three parents up = repo root), and `extra="forbid"` means a stray env var fails startup loudly.

`LOGFIRE_TOKEN` and `OTEL_SERVICE_NAME` are both optional but coupled — a `model_validator` refuses to start if `LOGFIRE_TOKEN` is set without `OTEL_SERVICE_NAME`. Service identity is explicit per deploy, never inferred. `MECHANISM_TOKEN` is required (no default); startup fails loudly if unset rather than silently running the FastMCP servers unauthenticated.

### Observability

The lifespan calls `logfire.instrument_mcp()` (covers all three mounted FastMCP servers) and the usual `instrument_httpx` / `instrument_asyncpg` / `instrument_openai`. A surgical scrubbing callback whitelists the `session_id` span attribute from Logfire's default `session` scrub pattern — Claude Code session UUIDs aren't sensitive, and they're the only join key we have between mechanism traces, CC's separate OTel stream, and Bifrost logs.

## Conventions

- Commit `uv.lock`. We're an application, not a library; reproducibility across machines and deploys wins.
- Dependency groups follow PEP 735 (`[dependency-groups]`); the `dev` group is special-cased and synced by default. Don't reach for `[project.optional-dependencies]` unless we're publishing.
- Build backend is `uv_build`.
