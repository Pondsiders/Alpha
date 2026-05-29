"""Baseline: Rosemary's pre-Alembic public-schema database.

This revision documents the schema as it existed before Alembic was
introduced. It is **stamped, never run**: ``alembic stamp`` writes this
revision id into ``alembic_version`` without executing ``upgrade()``,
because the tables already exist (restored from a prod dump). The schema
transform chain (issue #3) stacks on top of this marker.

Schema captured here (everything in ``public``; pgvector in ``public``):

- ``memories`` — ``embedding`` vector(768), ``content_tsv``, ``metadata``
  jsonb, ``forgotten`` bool; time lives in ``metadata->>'created_at'``
- ``sage_messages`` — Sage archive; ``embedding`` vector(768), ``content_tsv``
- ``sage_conversations`` — Sage conversation index (FK target of sage_messages)
- ``summaries`` — legacy old-stack table (currently empty)
- ``messages`` — legacy old-stack turn archive
- ``rosemary_sessions`` — legacy old-stack App session list

Revision ID: 5cf9fe952732
Revises:
Create Date: 2026-05-29 11:18:30.570435
"""

from __future__ import annotations

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "5cf9fe952732"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """No-op: the baseline schema predates Alembic and is stamped, not built.

    There is intentionally nothing to run — the database this revision
    represents already exists, so we ``alembic stamp`` it rather than
    ``upgrade`` from empty. The build-from-empty path, if ever needed, lives
    in ``tests/fixtures/schema.sql``, not here.
    """


def downgrade() -> None:
    """No-op: there is no pre-baseline state to downgrade to."""
