#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "openai>=1.0",
#     "pydantic-settings>=2.0",
# ]
# ///
"""Materialize seed.sql from seed.sql.template by filling in embeddings.

Reads `seed.sql.template`, finds every `{{EMBED:<text>}}` placeholder, calls
Bifrost (the embedding model production uses) once per unique text, and
substitutes the resulting 2560-float vector as a Postgres array literal.

Usage:
    cd <repo-root>
    just seed-generate

The output (`seed.sql`) is committed to git and loaded by conftest's `seeded`
fixture. Regenerate this file whenever the template changes or the embedding
model is swapped.
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path
from typing import ClassVar

from openai import AsyncOpenAI
from pydantic_settings import BaseSettings, SettingsConfigDict


class _Settings(BaseSettings):
    embedding_base_url: str
    embedding_api_key: str
    embedding_model: str

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


_PLACEHOLDER = re.compile(r"\{\{EMBED:(.+?)\}\}", re.DOTALL)


def _format_vector(vector: list[float]) -> str:
    """Format a float list as a Postgres array literal — `[v1,v2,...]`."""
    return "[" + ",".join(f"{x:.6f}" for x in vector) + "]"


async def main() -> int:
    here = Path(__file__).parent
    template_path = here / "seed.sql.template"
    output_path = here / "seed.sql"

    template = template_path.read_text(encoding="utf-8")

    unique_texts: list[str] = sorted(set(_PLACEHOLDER.findall(template)))
    if not unique_texts:
        print("No {{EMBED:...}} placeholders found; nothing to do.", file=sys.stderr)
        return 0

    settings = _Settings()  # pyright: ignore[reportCallIssue]
    client = AsyncOpenAI(
        base_url=settings.embedding_base_url,
        api_key=settings.embedding_api_key,
    )

    print(
        f"Embedding {len(unique_texts)} unique texts via {settings.embedding_model}...",
        file=sys.stderr,
    )
    response = await client.embeddings.create(
        model=settings.embedding_model,
        input=unique_texts,
    )

    text_to_vector: dict[str, str] = {
        text: _format_vector(data.embedding)
        for text, data in zip(unique_texts, response.data, strict=True)
    }

    def _replace(match: re.Match[str]) -> str:
        return text_to_vector[match.group(1)]

    materialized = _PLACEHOLDER.sub(_replace, template)
    _ = output_path.write_text(materialized, encoding="utf-8")

    relpath = output_path.relative_to(Path.cwd())
    kb = output_path.stat().st_size // 1024
    print(
        f"Wrote {relpath} ({len(unique_texts)} embeddings, {kb} KB).",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
