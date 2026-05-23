# Mechanism evals

Quantitative eval harness for the `/hooks/memories` extract-queries step.

## Why

The extract-queries prompt asks Qwen to turn a conversational message into a
list of search queries that get embedded and recalled against `cortex.memories`.
Issue [#13] documents the dominant failure mode: when a prompt has multiple
substantive topics, Qwen sometimes commits to one and silently drops the
others. We need to measure this quantitatively before iterating on the prompt
or extending the pipeline (e.g. an `/hooks/asides` companion).

## Shape

- **dataset**: hand-curated conversational prompts pulled from our
  conversation history (Jeffery's real prompts, not synthetic), each labeled
  with the topics the extract step *should* surface.
- **scoring**: two scores per case on different scales, deliberately not
  summed. Score(+) is the sum of best-match cosines over expected topics that
  hit at threshold τ (bounded `[0, N_expected_topics]`, measures correctness).
  Score(−) is the count of extracted queries that didn't match any expected
  topic (bounded `[0, ∞)`, measures over-extraction). Embeddings via Qwen 3
  Embedding 4B, the same model production uses.
- **stratification**: cases are bucketed by topic-count so per-stratum scores
  surface improvements on the multi-topic failure mode that aggregate scores
  would dilute.

Three strata:

| Tag | Meaning | Count |
|---|---|---|
| `S` | single substantive topic (baseline — is recall working at all?) | 7 |
| `M` | multi-substantive (the failure-mode stratum) | 12 |
| `P` | primary-topic + peripheral references (the should-filter stratum) | 6 |

## Layout

```
evals/
├── README.md              ← this file
├── seed_cases.yaml        ← committed: source-database row ids + hand-curated labels
├── extract_dataset.py     ← committed: seed_cases.yaml + source DB → data/dataset.yaml
├── run_eval.py            ← committed: prompt + dataset → cosine-sim scores → data/results.db
├── prompts/
│   └── v1-baseline.md     ← committed: snapshot of the current production prompt
└── data/                  ← gitignored: real prompt content + scoring results
    ├── dataset.yaml
    └── results.db
```

`seed_cases.yaml` (committed) holds the row ids and labels — enough to
reconstruct the dataset on any machine with source-DB access.
`data/dataset.yaml` (gitignored) holds the materialized content — real
conversational prompts from our history, pulled from a private DB.

## Bootstrap

From `mechanism/`:

```sh
uv sync
EVAL_SOURCE_DATABASE_URL=postgresql://... uv run python evals/extract_dataset.py
LOGFIRE_IGNORE_NO_CONFIG=1 uv run python evals/run_eval.py evals/prompts/v1-baseline.md
```

`EVAL_SOURCE_DATABASE_URL` is required for extraction — the script fails loud
if unset. Point it at a Postgres URL with read access to the conversation
history table this eval draws from.

`LOGFIRE_IGNORE_NO_CONFIG=1` for the runner suppresses logfire's "not
configured" warning (the eval bypasses the FastAPI lifespan so
`logfire.configure()` is never called).

Run output: per-case progress to stdout, plus stratified summary table, plus
one row per case persisted to `data/results.db` (table `runs`).

The paired-comparison tool (compare.py — for measuring v1-vs-v2 deltas with
McNemar / bootstrap CI) is not yet implemented.

[#13]: https://github.com/Pondsiders/Alpha/issues/13
