"""compare_prompts.py — promptfucking harness for any eval suite.

Compares the working-tree version of the suite's prompt against a git ref
(default HEAD), runs the eval k times per case in paired fashion, reports
per-metric mean deltas with bootstrap 95% confidence intervals, and
optionally auto-commits to the current branch when the F1 improvement is
statistically significant.

Caches per-case-per-sample results keyed by SHA256 of (prompt, dataset
content, samples, threshold, suite). This means: run the baseline once,
re-use it across iterations on the same branch; only the candidate side
needs re-running each tweak. As auto-commits ratchet the branch forward,
the cache rolls forward for free (the just-committed candidate hash IS the
new baseline hash; no re-run needed).

Auto-commit is opt-in (--auto-commit) and refuses on protected branches
(default: main) or detached HEAD. Stages only the suite's prompt file via
explicit `git add <path>` — never `-A`.

Usage (from mechanism/):
    uv run --group eval python -m evals.compare_prompts memories
    uv run --group eval python -m evals.compare_prompts memories --auto-commit
    uv run --group eval python -m evals.compare_prompts memories --baseline main --samples 5
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib
import json
import pickle
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import logfire
import numpy as np

from evals.suite import EvalSuite
from mechanism.settings import get_settings

CACHE_DIR = Path(__file__).resolve().parent / ".cache"
PROTECTED_BRANCHES = ("main",)
BOOTSTRAP_N = 10_000
HEADLINE_METRICS = ("precision", "recall", "f1")
GATE_METRIC = "f1"


def load_suite(name: str) -> EvalSuite:
    """Import evals.suites.<name>.config and return its SUITE constant."""
    module = importlib.import_module(f"evals.suites.{name}.config")
    return module.SUITE


# --- Git helpers ---


def _git(*args: str) -> str:
    """Run a git command, return stripped stdout. Raises on nonzero exit."""
    cmd = ["git", *args]
    # S603: git is a workshop tool, cmd is constructed locally from typed args.
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)  # noqa: S603
    return result.stdout


def current_branch() -> str | None:
    """Return current branch name, or None if HEAD is detached."""
    branch = _git("rev-parse", "--abbrev-ref", "HEAD").strip()
    return None if branch == "HEAD" else branch


def repo_root() -> Path:
    """Return the absolute path of the git repo root."""
    return Path(_git("rev-parse", "--show-toplevel").strip())


def read_prompt_at_ref(ref: str, path_relative_to_repo_root: Path) -> str:
    """Read a file's contents at a given git ref via `git show <ref>:<path>`."""
    return _git("show", f"{ref}:{path_relative_to_repo_root}")


def commit_prompt_change(file_path: Path, commit_message: str) -> str:
    """Stage only `file_path`, commit, return the new short SHA."""
    _ = _git("add", str(file_path))
    _ = _git("commit", "-m", commit_message)
    return _git("rev-parse", "--short", "HEAD").strip()


# --- Cache ---


def cache_key(
    *,
    prompt: str,
    dataset_hash: str,
    samples: int,
    threshold: float,
    suite_name: str,
) -> str:
    """Build a stable cache key from everything that affects the per-case results."""
    h = hashlib.sha256()
    for part in (prompt, dataset_hash, str(samples), f"{threshold:.6f}", suite_name):
        h.update(part.encode("utf-8"))
        h.update(b"\x1f")  # ASCII unit separator
    return h.hexdigest()


def cache_load(key: str) -> dict[str, list[dict[str, float]]] | None:
    """Return cached per-case-per-sample results, or None if missing."""
    path = CACHE_DIR / f"{key}.pkl"
    if not path.exists():
        return None
    with path.open("rb") as f:
        return pickle.load(f)  # noqa: S301 — local cache, never untrusted input


def cache_save(key: str, results: dict[str, list[dict[str, float]]]) -> None:
    """Persist per-case-per-sample results to the local cache."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with (CACHE_DIR / f"{key}.pkl").open("wb") as f:
        pickle.dump(results, f)


def dataset_content_hash(suite: EvalSuite) -> str:
    """Hash the loaded dataset's case contents so cache invalidates if data changes."""
    dataset = suite.load_dataset()
    serial = json.dumps(
        [
            {"name": c.name, "inputs": c.inputs, "expected_output": c.expected_output}
            for c in dataset.cases
        ],
        sort_keys=True,
    )
    return hashlib.sha256(serial.encode("utf-8")).hexdigest()


# --- Eval runner ---


async def run_eval_for_prompt(
    suite: EvalSuite,
    prompt: str,
    samples: int,
    max_concurrency: int,
    cases_limit: int = 0,
) -> dict[str, list[dict[str, float]]]:
    """Run the eval `samples` times for the given prompt; return per-case results.

    Returns a dict keyed by case name; each value is a list of length `samples`,
    where each entry is the {metric: value} score dict from CosineMatchEvaluator
    for that case-sample pair.
    """
    dataset = suite.load_dataset()
    if cases_limit > 0:
        dataset.cases = dataset.cases[:cases_limit]
    for evaluator in suite.evaluators:
        dataset.add_evaluator(evaluator)

    for case in dataset.cases:
        if case.name is None:
            raise ValueError(f"Case missing required name: {case!r}")
    per_case: dict[str, list[dict[str, float]]] = {
        case.name: [] for case in dataset.cases if case.name is not None
    }
    task = suite.make_task(prompt)

    for _ in range(samples):
        report = await dataset.evaluate(task, max_concurrency=max_concurrency)
        for case in report.cases:
            if case.name is None:
                raise ValueError(f"Report case missing name: {case!r}")
            per_case[case.name].append({k: float(v.value) for k, v in case.scores.items()})

    return per_case


# --- Comparison ---


@dataclass
class MetricDelta:
    """Per-metric comparison result with bootstrap CI."""

    name: str
    baseline_mean: float
    candidate_mean: float
    delta: float
    ci_low: float
    ci_high: float

    @property
    def significant_win(self) -> bool:
        """True iff the 95% CI on the delta is strictly above 0."""
        return self.ci_low > 0

    @property
    def significant_loss(self) -> bool:
        """True iff the 95% CI on the delta is strictly below 0."""
        return self.ci_high < 0


@dataclass
class Comparison:
    """Per-metric deltas plus run shape (cases x samples)."""

    per_metric: dict[str, MetricDelta]
    total_cases: int
    samples_per_case: int


def compare(
    baseline_results: dict[str, list[dict[str, float]]],
    candidate_results: dict[str, list[dict[str, float]]],
    metrics: tuple[str, ...] = HEADLINE_METRICS,
    bootstrap_n: int = BOOTSTRAP_N,
) -> Comparison:
    """Compute per-metric mean deltas with bootstrap 95% CIs (paired by case)."""
    case_names = sorted(set(baseline_results.keys()) & set(candidate_results.keys()))
    rng = np.random.default_rng(seed=42)
    per_metric: dict[str, MetricDelta] = {}

    for metric in metrics:
        baseline_per_case = np.array(
            [np.mean([s[metric] for s in baseline_results[name]]) for name in case_names]
        )
        candidate_per_case = np.array(
            [np.mean([s[metric] for s in candidate_results[name]]) for name in case_names]
        )
        delta_per_case = candidate_per_case - baseline_per_case

        n = len(case_names)
        boot_means = np.empty(bootstrap_n)
        for i in range(bootstrap_n):
            idx = rng.integers(0, n, n)
            boot_means[i] = float(np.mean(delta_per_case[idx]))

        per_metric[metric] = MetricDelta(
            name=metric,
            baseline_mean=float(np.mean(baseline_per_case)),
            candidate_mean=float(np.mean(candidate_per_case)),
            delta=float(np.mean(delta_per_case)),
            ci_low=float(np.percentile(boot_means, 2.5)),
            ci_high=float(np.percentile(boot_means, 97.5)),
        )

    samples_per_case = len(baseline_results[case_names[0]]) if case_names else 0
    return Comparison(
        per_metric=per_metric, total_cases=len(case_names), samples_per_case=samples_per_case
    )


# --- Approach lights + reporting ---


def safety_check(
    *, auto_commit: bool, protected: tuple[str, ...] = PROTECTED_BRANCHES
) -> str | None:
    """Validate auto-commit safety. Return error string if a check fails, else None."""
    if not auto_commit:
        return None
    branch = current_branch()
    if branch is None:
        return "⛔ Refusing to auto-commit: HEAD is detached (no branch to commit to)."
    if branch in protected:
        return (
            f"⛔ Refusing to auto-commit on protected branch '{branch}'.\n"
            f"   Create a branch first: git checkout -b prompt-vN-<description>"
        )
    return None


def print_approach_lights(suite: EvalSuite, *, auto_commit: bool, baseline_ref: str) -> None:
    """Print the safety state before running, so you see what's about to happen."""
    branch = current_branch() or "(detached HEAD)"
    print(f"✓ Suite:        {suite.name}")
    print(f"✓ Branch:       {branch}")
    print(f"✓ Baseline ref: {baseline_ref}")
    print(f"✓ Prompt file:  {suite.prompt_path.name}")
    if auto_commit:
        print(f"✓ Auto-commit:  ON (will fire on significant {GATE_METRIC.upper()} improvement)")
    else:
        print("✓ Auto-commit:  OFF (report only)")


def print_comparison(comparison: Comparison, baseline_ref: str) -> None:
    """Print per-metric delta table with CI and win/loss marker."""
    print(
        f"\n=== Comparison vs {baseline_ref} "
        f"({comparison.total_cases} cases x {comparison.samples_per_case} samples) ===\n"
    )
    for name, m in comparison.per_metric.items():
        if m.significant_win:
            marker = "✅ win"
        elif m.significant_loss:
            marker = "❌ loss"
        else:
            marker = "⚠  no sig diff"
        print(
            f"  {name:9s}: {m.baseline_mean:.3f} → {m.candidate_mean:.3f}   "
            f"Δ {m.delta:+.4f}   95% CI [{m.ci_low:+.4f}, {m.ci_high:+.4f}]   {marker}"
        )


def auto_commit_message(suite: EvalSuite, comparison: Comparison, baseline_sha: str) -> str:
    """Generate a conventional-commit message documenting the deltas."""
    f1 = comparison.per_metric["f1"]
    precision = comparison.per_metric["precision"]
    recall = comparison.per_metric["recall"]
    summary = (
        f"feat({suite.name}): prompt iteration — "
        f"F1 {f1.delta:+.3f}, precision {precision.delta:+.3f}, recall {recall.delta:+.3f}"
    )
    body = "\n".join(
        [
            f"Bootstrap n={BOOTSTRAP_N} over {comparison.total_cases} cases x "
            f"{comparison.samples_per_case} samples per case.",
            f"Baseline: {baseline_sha}",
            "",
            f"F1:        {f1.baseline_mean:.3f} → {f1.candidate_mean:.3f}   "
            f"95% CI [{f1.ci_low:+.4f}, {f1.ci_high:+.4f}]",
            f"Precision: {precision.baseline_mean:.3f} → {precision.candidate_mean:.3f}   "
            f"95% CI [{precision.ci_low:+.4f}, {precision.ci_high:+.4f}]",
            f"Recall:    {recall.baseline_mean:.3f} → {recall.candidate_mean:.3f}   "
            f"95% CI [{recall.ci_low:+.4f}, {recall.ci_high:+.4f}]",
        ]
    )
    return f"{summary}\n\n{body}"


# --- Main ---


def _threshold_from_suite(suite: EvalSuite, default: float = 0.70) -> float:
    """Best-effort extraction of the evaluator's threshold for cache-key purposes."""
    for evaluator in suite.evaluators:
        t = getattr(evaluator, "threshold", None)
        if t is not None:
            return float(t)
    return default


def main() -> None:
    """Parse args, run safety check, run baseline + candidate evals, print comparison."""
    parser = argparse.ArgumentParser(
        description="Compare a suite's working-tree prompt against a git ref."
    )
    parser.add_argument("suite", help="Suite name (e.g. 'memories').")
    parser.add_argument(
        "--baseline", default="HEAD", help="Git ref for the baseline (default: HEAD)."
    )
    parser.add_argument("--samples", type=int, default=3, help="Samples per case (default 3).")
    parser.add_argument("--cases", type=int, default=0, help="Limit to N cases (0 = all).")
    parser.add_argument("--max-concurrency", type=int, default=4)
    parser.add_argument("--auto-commit", action="store_true", help="Commit on significant F1 win.")
    args = parser.parse_args()

    suite = load_suite(args.suite)

    err = safety_check(auto_commit=args.auto_commit)
    if err:
        print(err)
        sys.exit(1)

    settings = get_settings()
    _ = logfire.configure(
        send_to_logfire="if-token-present",
        token=settings.logfire_token,
        service_name=f"mechanism-eval-{suite.name}-compare",
    )
    logfire.instrument_httpx()
    _ = logfire.instrument_openai()

    print_approach_lights(suite, auto_commit=args.auto_commit, baseline_ref=args.baseline)

    # Resolve prompts (baseline from git, candidate from disk).
    root = repo_root()
    rel_prompt_path = suite.prompt_path.resolve().relative_to(root)
    baseline_prompt = read_prompt_at_ref(args.baseline, rel_prompt_path)
    candidate_prompt = suite.prompt_path.read_text(encoding="utf-8")

    if baseline_prompt == candidate_prompt:
        print(f"\n⚠  Working tree is identical to {args.baseline}; nothing to compare.")
        return

    # Cache keys (everything that affects per-case results).
    ds_hash = dataset_content_hash(suite)
    threshold = _threshold_from_suite(suite)
    common_kwargs: dict[str, Any] = {
        "dataset_hash": ds_hash,
        "samples": args.samples,
        "threshold": threshold,
        "suite_name": suite.name,
    }
    baseline_key = cache_key(prompt=baseline_prompt, **common_kwargs)
    candidate_key = cache_key(prompt=candidate_prompt, **common_kwargs)

    # Baseline (cached if we've evaluated this exact prompt+config before).
    baseline_results = cache_load(baseline_key)
    if baseline_results is None:
        print(f"\nRunning baseline eval ({args.samples} samples)...")
        baseline_results = asyncio.run(
            run_eval_for_prompt(
                suite, baseline_prompt, args.samples, args.max_concurrency, args.cases
            )
        )
        cache_save(baseline_key, baseline_results)
    else:
        print(f"\n✓ Baseline cached ({len(baseline_results)} cases).")

    # Candidate (cached if we've evaluated this exact working-tree prompt before).
    candidate_results = cache_load(candidate_key)
    if candidate_results is None:
        print(f"Running candidate eval ({args.samples} samples)...")
        candidate_results = asyncio.run(
            run_eval_for_prompt(
                suite, candidate_prompt, args.samples, args.max_concurrency, args.cases
            )
        )
        cache_save(candidate_key, candidate_results)
    else:
        print("✓ Candidate cached.")

    comparison = compare(baseline_results, candidate_results)
    print_comparison(comparison, args.baseline)

    if args.auto_commit:
        gate = comparison.per_metric[GATE_METRIC]
        if gate.significant_win:
            baseline_sha = _git("rev-parse", "--short", "HEAD").strip()
            message = auto_commit_message(suite, comparison, baseline_sha)
            print(f"\n=== Auto-committing {GATE_METRIC.upper()} win ===\n{message}\n")
            new_sha = commit_prompt_change(suite.prompt_path, message)
            print(f"✓ Committed: {new_sha}")
        else:
            metric = GATE_METRIC.upper()
            print(f"\n— No significant {metric} improvement (CI crosses 0); not committing.")


if __name__ == "__main__":
    main()
