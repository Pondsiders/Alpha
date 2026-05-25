"""Nondenominational runner for any eval suite.

Loads a suite from `evals.suites.<name>.config`, reads the production
prompt from disk, runs the eval against the suite's dataset, and prints
the report. Same code path for any prompt — memories, anamneses, or
anything we add later. The harness knows nothing about what's inside
the suite.

Usage (from mechanism/):
    uv run --group eval python -m evals.run <suite>

Example:
    uv run --group eval python -m evals.run memories
"""

from __future__ import annotations

import argparse
import importlib

import logfire

from evals.suite import EvalSuite
from mechanism.settings import get_settings


def load_suite(name: str) -> EvalSuite:
    """Import evals.suites.<name>.config and return its SUITE constant."""
    module = importlib.import_module(f"evals.suites.{name}.config")
    return module.SUITE


def main() -> None:
    """Parse args, load suite, run eval, print report."""
    parser = argparse.ArgumentParser(description="Run an eval suite end-to-end.")
    parser.add_argument("suite", help="Name of the eval suite (e.g., 'memories').")
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=4,
        help="Max concurrent cases (default 4 to match llama-server --parallel 4).",
    )
    args = parser.parse_args()

    suite = load_suite(args.suite)

    settings = get_settings()
    _ = logfire.configure(
        send_to_logfire="if-token-present",
        token=settings.logfire_token,
        service_name=f"mechanism-eval-{suite.name}",
    )
    logfire.instrument_httpx()
    _ = logfire.instrument_openai()

    prompt = suite.prompt_path.read_text(encoding="utf-8")
    dataset = suite.load_dataset()
    for evaluator in suite.evaluators:
        dataset.add_evaluator(evaluator)
    for report_evaluator in suite.report_evaluators:
        dataset.report_evaluators.append(report_evaluator)

    task = suite.make_task(prompt)

    print(
        f"Running suite '{suite.name}' "
        f"(prompt: {suite.prompt_path.name}, {len(prompt)} chars) "
        f"against {len(dataset.cases)} cases..."
    )

    report = dataset.evaluate_sync(task, max_concurrency=args.max_concurrency)
    report.print(include_input=False, include_output=False, include_durations=False)


if __name__ == "__main__":
    main()
