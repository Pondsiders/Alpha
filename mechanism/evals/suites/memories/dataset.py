"""Pydantic Evals Dataset for the /hooks/memories prompt eval.

Loads sample-100-labeled.json (hand-labeled by Alpha, May 23 2026) into a
Pydantic Evals Dataset. Skips rows flagged as contamination (e.g. Solitude
self-prompts that snuck through prefix filtering).

Each Case:
  - inputs:           the user message text
  - expected_output:  the list of golden query strings (may be empty for
                      empty-correct cases like "Okay, here goes!")
  - metadata:         {id, timestamp, session_id} for traceability
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic_evals import Case, Dataset

SAMPLE_FILE = Path(__file__).parent / "sample-100-labeled.json"


def load_dataset() -> Dataset[str, list[str], dict[str, Any]]:
    """Load the labeled sample into a Pydantic Evals Dataset, skipping flagged rows."""
    rows = json.loads(SAMPLE_FILE.read_text())
    cases = [
        Case(
            name=f"msg-{row['id']}",
            inputs=row["content"],
            expected_output=row["queries"],
            metadata={
                "id": row["id"],
                "timestamp": row["timestamp"],
                "session_id": row["session_id"],
            },
        )
        for row in rows
        if "flag" not in row
    ]
    return Dataset(name="memories-prompt-eval", cases=cases)


if __name__ == "__main__":
    dataset = load_dataset()
    print(f"Loaded {len(dataset.cases)} cases (after dropping flagged rows)")
    n_empty = sum(1 for c in dataset.cases if not c.expected_output)
    print(f"  Empty-correct cases: {n_empty}")
    print(f"  Substantive cases: {len(dataset.cases) - n_empty}")
    print()
    print("First three cases:")
    for c in dataset.cases[:3]:
        preview = c.inputs[:80].replace("\n", " ")
        expected = c.expected_output or []
        more = "..." if len(expected) > 2 else ""
        print(f"  {c.name}  inputs={preview!r}")
        print(f"           expected={expected[:2]}{more}")
