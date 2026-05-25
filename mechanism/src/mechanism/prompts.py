"""Prompt loader: load a named prompt from ``mechanism/prompts/<name>.md``.

The ``prompts/`` directory sits at the repo-root level of ``mechanism/``
(beside ``evals/``, ``src/``, ``tests/``) rather than inside the Python
package, because the prompts are *data* the package reads, not code the
package exports.

The bundle is per-deploy. In Alpha's repo, ``prompts/*.md`` contains
Alpha's prompts; in Rosemary's repo (post-fork), the same paths contain
Rosemary's prompts. Cross-deploy merges produce conflicts on prompt
files; resolution is by hand, keeping the local deploy's version and
optionally porting improvements from the other side. The repo identity
IS the deploy identity.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

# This module lives at mechanism/src/mechanism/prompts.py. The prompts
# directory lives at mechanism/prompts/. Three .parent calls climb out
# of the package layout (.../src/mechanism/) and back up to mechanism/.
PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


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
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt '{name}' missing at {path}")
    return path.read_text(encoding="utf-8")


__all__ = ["PROMPTS_DIR", "get_prompt"]
