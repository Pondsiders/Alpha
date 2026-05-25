"""Prompt loader: load a named prompt from ``prompts/<name>.md``.

The ``prompts/`` directory is per-deploy. In Alpha's repo it carries
Alpha's prompts; in Rosemary's repo (post-fork) it carries Rosemary's
prompts at the same paths. Cross-deploy merges produce conflicts on
prompt files; resolution is by hand, keeping the local deploy's
version and optionally porting improvements from the other side.

The repo identity IS the deploy identity. No env-var selection; no
per-deploy subdirs. Each repo carries its own prompts and only its own.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parent


@cache
def get_prompt(name: str) -> str:
    """Load ``prompts/<name>.md`` and return its contents as a string.

    Args:
        name: Prompt file basename without the ``.md`` extension
            (e.g. ``"memories_system"``).

    Returns:
        The prompt file's contents as a UTF-8 string.

    Raises:
        FileNotFoundError: if the named prompt file does not exist.
    """
    path = _PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt '{name}' missing at {path}")
    return path.read_text(encoding="utf-8")


__all__ = ["get_prompt"]
