# Production image for alpha-server.

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Cache deps separately from source so source-only edits don't
# rebuild the deps layer.
COPY alpha-server/pyproject.toml alpha-server/uv.lock /app/alpha-server/
RUN cd /app/alpha-server && uv sync --frozen --no-install-project --no-dev

# Now the source.
COPY alpha-server/ /app/alpha-server/
RUN cd /app/alpha-server && uv sync --frozen --no-dev

ENV PATH="/app/alpha-server/.venv/bin:${PATH}"

WORKDIR /app/alpha-server

EXPOSE 8000

# Bind to 0.0.0.0 inside the container; the compose port-mapping
# restricts external reach to 127.0.0.1 on the host.
CMD ["uvicorn", "alpha_server.app:app", "--host", "0.0.0.0", "--port", "8000"]
