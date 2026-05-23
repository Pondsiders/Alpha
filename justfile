# Alpha dev environment recipes.
# Run from the repo root: `just <recipe>`.

# List recipes.
default:
    @just --list

# Start the dev environment (Postgres, Redis, and alpha-server on localhost:8001).
dev-up:
    docker compose -f compose-dev.yml up -d

# Stop the dev environment (preserves the data volumes).
dev-down:
    docker compose -f compose-dev.yml down

# Tail container logs. Forwards args, so `just dev-logs -f alpha-server` works.
dev-logs *args:
    docker compose -f compose-dev.yml logs {{args}}

# Wipe Postgres AND Redis data volumes, bring services up fresh, restore Postgres from a dump.
dev-init dump:
    docker compose -f compose-dev.yml down -v
    docker compose -f compose-dev.yml up -d
    @echo "(waiting for postgres to accept connections)"
    @until docker compose -f compose-dev.yml exec -T postgres pg_isready -U postgres >/dev/null 2>&1; do sleep 1; done
    docker compose -f compose-dev.yml exec -T postgres pg_restore \
        --username=postgres \
        --dbname=postgres \
        --single-transaction \
        --no-owner \
        --no-acl \
        < {{dump}}

# Start the isolated test stack (Postgres on 127.0.0.1:55432, Redis on 127.0.0.1:56379).
test-up:
    docker compose -f compose-test.yml up -d --wait

# Stop the test stack (preserves the data volume).
test-down:
    docker compose -f compose-test.yml down

# Wipe the test Postgres volume, bring services up fresh, load schema.sql.
test-init:
    docker compose -f compose-test.yml down -v
    docker compose -f compose-test.yml up -d --wait
    docker compose -f compose-test.yml exec -T postgres psql \
        --username=postgres \
        --dbname=postgres \
        --single-transaction \
        < mechanism/tests/fixtures/schema.sql

# Run the pytest suite against the test stack.
# Sets TEST_DATABASE_URL/TEST_REDIS_URL pointing at compose-test's services;
# conftest.py rewrites DATABASE_URL/REDIS_URL from them at session start.
test: test-up
    cd mechanism && \
        TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55432/postgres \
        TEST_REDIS_URL=redis://127.0.0.1:56379/0 \
        LOGFIRE_IGNORE_NO_CONFIG=1 \
        uv run pytest

# Wipe and re-init the test stack, then run the suite.
test-reset: test-init test

# Materialize seed.sql by filling embeddings into seed.sql.template via Bifrost.
# Run after editing the template, or after swapping embedding models.
seed-generate:
    ./mechanism/tests/fixtures/generate.py
