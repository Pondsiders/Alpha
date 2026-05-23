"""Run an extract-queries prompt against the materialized dataset, score, persist.

Run from `mechanism/`:
    uv run python evals/run_eval.py evals/prompts/v1-baseline.md

For each case in `data/dataset.yaml`, calls the chat model with the given
prompt as system + the case content as user, parses the JSON array response,
scores via `score.score_case`, and writes one row per case to
`data/results.db` (table `runs`).

Settings:
- LOGFIRE_IGNORE_NO_CONFIG=1 is recommended (the eval doesn't run the FastAPI
  lifespan, so logfire.configure() is never called; this env var suppresses
  the noisy warning).
- Chat/embedding endpoints come from the project .env via mechanism.settings.

Brittle as fuck: raises on JSON parse failure (with full raw response in the
message) so a misbehaving prompt fails the run loudly instead of being buried
in averages.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
import yaml
from numpy.typing import NDArray

from mechanism import clock, llm

_EVALS_DIR = Path(__file__).resolve().parent
_DATA_DIR = _EVALS_DIR / "data"
_DATASET_FILE = _DATA_DIR / "dataset.yaml"
_RESULTS_DB = _DATA_DIR / "results.db"


@dataclass(frozen=True)
class _ScoreResult:
    """Per-case scoring result.

    Two scores on different scales, deliberately not summed:
      score_plus  — sum of best-match cosines over expected topics that were hit.
                    Bounded [0, N_expected_topics]. Measures extraction correctness.
      score_minus — count of extracted queries that didn't match any expected
                    topic above threshold. Bounded [0, ∞). Measures over-extraction.
    """

    per_topic_hits: dict[str, dict[str, float | bool]]
    score_plus: float
    score_minus: int


async def _embed_many(texts: list[str]) -> NDArray[np.float32]:
    """Embed and L2-normalize a list of strings, return (N, D) float32 array."""
    client = llm.get_embedding_client()
    model = llm.get_embedding_model()
    formatted = [llm.format_query_for_embedding(t) for t in texts]
    resp = await client.embeddings.create(model=model, input=formatted)
    vecs = np.asarray([d.embedding for d in resp.data], dtype=np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True).astype(np.float32)
    return (vecs / np.where(norms > 0, norms, np.float32(1.0))).astype(np.float32)


async def _score_case(
    extracted_queries: list[str],
    expected_topics: list[str],
    threshold: float,
) -> _ScoreResult:
    """Score one case via cosine similarity at the given threshold."""
    if not expected_topics:
        msg = "expected_topics is empty — bad seed_cases entry"
        raise ValueError(msg)

    if not extracted_queries:
        per_topic: dict[str, dict[str, float | bool]] = {
            t: {"hit": False, "max_cos": 0.0} for t in expected_topics
        }
        return _ScoreResult(per_topic_hits=per_topic, score_plus=0.0, score_minus=0)

    topic_vecs = await _embed_many(expected_topics)
    query_vecs = await _embed_many(extracted_queries)
    sims = (topic_vecs @ query_vecs.T).astype(np.float32)

    max_per_topic = sims.max(axis=1)
    topic_hits = max_per_topic >= threshold

    max_per_query = sims.max(axis=0)
    query_hits = max_per_query >= threshold

    per_topic = {
        topic: {"hit": bool(topic_hits[i]), "max_cos": float(max_per_topic[i])}
        for i, topic in enumerate(expected_topics)
    }
    score_plus = float(max_per_topic[topic_hits].sum()) if topic_hits.any() else 0.0
    score_minus = int((~query_hits).sum())
    return _ScoreResult(per_topic_hits=per_topic, score_plus=score_plus, score_minus=score_minus)


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the `runs` table if it doesn't exist."""
    _ = conn.execute(
        """
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prompt_version TEXT NOT NULL,
            run_timestamp TEXT NOT NULL,
            threshold REAL NOT NULL,
            case_id INTEGER NOT NULL,
            stratum TEXT NOT NULL,
            extracted_queries TEXT NOT NULL,
            per_topic_hits TEXT NOT NULL,
            score_plus REAL NOT NULL,
            score_minus INTEGER NOT NULL
        )
        """
    )
    _ = conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_runs_version_ts ON runs (prompt_version, run_timestamp)"
    )


def _parse_queries(raw: str, case_id: int) -> list[str]:
    """Parse the model's response as a JSON array of strings. Raise loudly otherwise."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        parsed: Any = json.loads(text)
    except json.JSONDecodeError as e:
        msg = f"case {case_id}: response not valid JSON: {raw!r}"
        raise ValueError(msg) from e
    if not isinstance(parsed, list):
        msg = f"case {case_id}: expected JSON array, got: {parsed!r}"
        raise ValueError(msg)
    parsed_list = cast(list[Any], parsed)
    queries: list[str] = []
    for q in parsed_list:
        if not isinstance(q, str):
            msg = f"case {case_id}: expected array of strings, got: {parsed!r}"
            raise ValueError(msg)
        queries.append(q)
    return queries


async def _extract_queries(case_content: str, system_prompt: str, case_id: int) -> list[str]:
    """Call the chat model with the prompt + case content, parse the result."""
    chat = llm.get_chat_client()
    model = llm.get_chat_model()
    resp = await chat.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": case_content},
        ],
        temperature=0,
    )
    raw = resp.choices[0].message.content or ""
    return _parse_queries(raw, case_id)


def _print_summary(rows: list[dict[str, Any]]) -> None:
    """Print per-stratum + overall two-score table.

    The two scores are deliberately not summed (they're on different scales).
    Score(+) is the sum of best-match cosines; Max(+) is the per-stratum total
    expected-topic count, the perfect-score upper bound. Score(-) is total
    false-positive query count.
    """
    by_stratum: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_stratum[r["stratum"]].append(r)

    header = (
        f"{'Stratum':<10}{'N':>4}{'Score(+)':>10}{'Max(+)':>8}"
        f"{'+ ratio':>9}{'Score(-)':>10}{'-/case':>8}"
    )
    print()
    print(header)
    print("-" * len(header))
    for stratum in ["S", "M", "P"]:
        bucket = by_stratum.get(stratum, [])
        if not bucket:
            continue
        sp = sum(r["score_plus"] for r in bucket)
        mp = sum(r["max_plus"] for r in bucket)
        sm = sum(r["score_minus"] for r in bucket)
        ratio = sp / mp if mp > 0 else 0.0
        per_case = sm / len(bucket)
        print(
            f"{stratum:<10}{len(bucket):>4}{sp:>10.2f}{mp:>8}{ratio:>9.3f}{sm:>10}{per_case:>8.2f}"
        )
    sp_tot = sum(r["score_plus"] for r in rows)
    mp_tot = sum(r["max_plus"] for r in rows)
    sm_tot = sum(r["score_minus"] for r in rows)
    ratio_tot = sp_tot / mp_tot if mp_tot > 0 else 0.0
    per_case_tot = sm_tot / len(rows)
    print("-" * len(header))
    print(
        f"{'Overall':<10}{len(rows):>4}{sp_tot:>10.2f}{mp_tot:>8}"
        + f"{ratio_tot:>9.3f}{sm_tot:>10}{per_case_tot:>8.2f}"
    )


async def _main() -> None:
    """Load dataset, run prompt against every case, persist + summarize."""
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("prompt", type=Path, help="Path to the system prompt file.")
    _ = parser.add_argument(
        "--threshold", type=float, default=0.55, help="Cosine threshold for hit (default 0.55)."
    )
    args = parser.parse_args()

    prompt_path: Path = args.prompt
    threshold: float = args.threshold
    if not prompt_path.is_file():
        msg = f"prompt file not found: {prompt_path}"
        raise FileNotFoundError(msg)

    system_prompt = prompt_path.read_text(encoding="utf-8")
    version = prompt_path.stem  # e.g. "v1-baseline" from "v1-baseline.md"

    if not _DATASET_FILE.is_file():
        msg = f"dataset not found: {_DATASET_FILE} (run extract_dataset.py first)"
        raise FileNotFoundError(msg)
    dataset = yaml.safe_load(_DATASET_FILE.read_text(encoding="utf-8"))
    cases: list[dict[str, Any]] = dataset["cases"]

    _DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(_RESULTS_DB)
    _ensure_schema(conn)

    run_ts = clock.now().isoformat()
    print(f"Running '{version}' against {len(cases)} cases (threshold={threshold})")
    print()

    rows: list[dict[str, Any]] = []
    for case in cases:
        case_id: int = case["id"]
        queries = await _extract_queries(case["content"], system_prompt, case_id)
        result = await _score_case(queries, case["expected_topics"], threshold)
        row = {
            "prompt_version": version,
            "run_timestamp": run_ts,
            "threshold": threshold,
            "case_id": case_id,
            "stratum": case["stratum"],
            "extracted_queries": json.dumps(queries),
            "per_topic_hits": json.dumps(result.per_topic_hits),
            "score_plus": result.score_plus,
            "score_minus": result.score_minus,
            # max_plus isn't stored — derivable from per_topic_hits — but kept in-row
            # for the summary print to avoid re-parsing JSON.
            "max_plus": len(case["expected_topics"]),
        }
        _ = conn.execute(
            """
            INSERT INTO runs (
                prompt_version, run_timestamp, threshold, case_id, stratum,
                extracted_queries, per_topic_hits, score_plus, score_minus
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["prompt_version"],
                row["run_timestamp"],
                row["threshold"],
                row["case_id"],
                row["stratum"],
                row["extracted_queries"],
                row["per_topic_hits"],
                row["score_plus"],
                row["score_minus"],
            ),
        )
        rows.append(row)
        stratum = case["stratum"]
        nq = len(queries)
        hits = sum(1 for h in result.per_topic_hits.values() if h["hit"])
        n_topics = len(result.per_topic_hits)
        sp = result.score_plus
        sm = result.score_minus
        print(f"  {case_id:>6} [{stratum}] q={nq:>2} hits={hits}/{n_topics} +{sp:.2f} -{sm}")

    conn.commit()
    conn.close()
    _print_summary(rows)


if __name__ == "__main__":
    asyncio.run(_main())
