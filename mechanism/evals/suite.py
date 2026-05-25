"""EvalSuite — the bundle of {prompt, dataset, task, evaluators} for one prompt-under-test.

The harness (run.py, compare_prompts.py) is nondenominational: it accepts a
suite and runs it, knowing nothing about what's inside. Each prompt that
wants to be evaluated lives at evals/suites/<name>/config.py with a
SUITE = EvalSuite(...) constant.

Adding a new suite is the work of creating the per-suite directory plus
(usually) labeling its dataset. The evaluator and task factory can often
be reused — memories and anamneses both want list-of-strings outputs
scored with set-based precision/recall/F1, so they share evaluator code
and have nearly identical task functions.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic_evals import Dataset
from pydantic_evals.evaluators import Evaluator, ReportEvaluator


@dataclass
class EvalSuite:
    """Bundle of the four things a prompt-under-test needs to be evaluated.

    Attributes:
        name: Short identifier (e.g., "memories", "anamneses"). Used for CLI
            argument matching and approach-lights output.
        prompt_path: Absolute path to the production prompt file. The harness
            reads this from disk for the candidate side and from git for the
            baseline side.
        load_dataset: Factory that returns the Pydantic Evals Dataset.
        make_task: Factory that takes a prompt string and returns an async
            task callable suitable for dataset.evaluate_sync(task).
        evaluators: Per-case evaluators to register on the dataset.
        report_evaluators: Report-level evaluators to register on the dataset.
    """

    name: str
    prompt_path: Path
    load_dataset: Callable[[], Dataset[Any, Any, Any]]
    make_task: Callable[[str], Callable[[str], Awaitable[Any]]]
    evaluators: list[Evaluator[Any, Any, Any]] = field(default_factory=list)
    report_evaluators: list[ReportEvaluator[Any, Any, Any]] = field(default_factory=list)
