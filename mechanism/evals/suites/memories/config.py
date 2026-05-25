"""Eval suite config for the memories prompt.

Wires together the four pieces the nondenominational harness needs:
the production prompt path, the dataset loader, the task factory, and
the evaluators. Exports `SUITE` for `evals.run` / `evals.compare_prompts`
to look up via `evals.suites.memories.config:SUITE`.
"""

from __future__ import annotations

from evals.cosine_match import CosineMatchEvaluator, MicroAveragedPRF1
from evals.suite import EvalSuite
from evals.suites.memories.dataset import load_dataset
from evals.suites.memories.task import make_task
from mechanism.prompts import PROMPTS_DIR

PROMPT_PATH = PROMPTS_DIR / "memories_system.md"

SUITE = EvalSuite(
    name="memories",
    prompt_path=PROMPT_PATH,
    load_dataset=load_dataset,
    make_task=make_task,
    evaluators=[CosineMatchEvaluator(threshold=0.70)],
    report_evaluators=[MicroAveragedPRF1()],
)
