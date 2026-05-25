"""Cosine-match Evaluator and micro-averaging ReportEvaluator for the memories prompt eval.

Per-case evaluation: greedy 1-to-1 cosine matching of Qwen queries against
golden references, then standard set-based precision/recall/F1. This is the
classical NER-shape multi-label-extraction evaluation; after the matching
step produces K (matches), P = K/Q, R = K/L, F1 = 2K/(L+Q).

Report-level evaluation: micro-averaged P/R/F1 across all cases. Micro
sums K/L/Q first, then computes one P/R/F1 from the totals, so every
prediction counts equally regardless of which case it came from and L=0
cases just contribute 0 to the sums without breaking anything. This is
the canonical headline metric for variable-cardinality multi-label
extraction. Macro averaging (per-case P/R/F1 then unweighted average)
falls out of the framework's ReportCaseAggregate.average() for free; the
macro-vs-micro gap is a diagnostic.

Per-pair cosine details are still emitted to Logfire as a span per case.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import logfire
import numpy as np
from pydantic_evals.evaluators import (
    Evaluator,
    EvaluatorContext,
    ReportEvaluator,
    ReportEvaluatorContext,
)
from pydantic_evals.reporting.analyses import ReportAnalysis, ScalarResult

from mechanism.llm import (
    format_query_for_embedding,
    get_embedding_client,
    get_embedding_model,
)


@dataclass
class CosineMatchEvaluator(Evaluator[str, list[str]]):
    """Greedy 1-to-1 cosine matching, returning per-case P/R/F1 plus raw counts.

    Per case:
      - Embed both lists via Bifrost (same client as production).
      - Build the LxQ cosine matrix.
      - For each golden in order: take the highest-cosine unconsumed Qwen
        query above threshold as a match; remove it from the pool.
      - Compute K=matches, then P=K/Q, R=K/L, F1=2K/(L+Q).

    Edge cases:
      - L=0, Q=0 → P=1, R=1, F1=1 (perfect empty-correct case)
      - L=0, Q>0 → P=0, R=0, F1=0 (over-extraction on empty-correct)
      - L>0, Q=0 → P=0, R=0, F1=0 (silent failure)

    Returned dict (each numeric value becomes a per-case "score" in the report):
      precision, recall, f1, matches, missed, false_positives, L, Q

    The K/L/Q counts ride along so the MicroAveragedPRF1 ReportEvaluator
    can sum them across the whole run.

    Embedding format defaults to DOCUMENT-MODE (no query wrapper) because
    we're doing query↔query similarity, not query→document retrieval. The
    asymmetry of Qwen 3 Embedding 4B's training means the query wrapper is
    wrong for symmetric comparison; document-mode gave +120 points across
    98 cases vs. query-mode on the same data (see comparison script).
    Toggle via `use_query_wrapper=True` to reproduce the old measurement.

    Greedy is order-dependent (not optimal). For our use case the
    distinction rarely matters since same-topic queries cluster tightly;
    a Hungarian-optimal version (scipy.optimize.linear_sum_assignment) is
    an optimization for later.
    """

    threshold: float = 0.70
    use_query_wrapper: bool = False

    async def evaluate(self, ctx: EvaluatorContext[str, list[str]]) -> dict[str, int | float]:
        """Score one case: returns dict of named metrics. See class docstring."""
        golden = ctx.expected_output or []
        qwen = ctx.output or []
        L = len(golden)
        Q = len(qwen)

        # Edge cases with no embedding needed.
        if L == 0 and Q == 0:
            return self._emit(ctx, L, Q, 0, [], [], [], precision=1.0, recall=1.0, f1=1.0)
        if L == 0:
            return self._emit(ctx, L, Q, 0, [], [], qwen, precision=0.0, recall=0.0, f1=0.0)
        if Q == 0:
            missed = [{"label": g, "best_cos": None} for g in golden]
            return self._emit(ctx, L, Q, 0, [], missed, [], precision=0.0, recall=0.0, f1=0.0)

        # Embed both lists. Two batch calls per case.
        client = get_embedding_client()
        model = get_embedding_model()
        if self.use_query_wrapper:
            golden_inputs = [format_query_for_embedding(q) for q in golden]
            qwen_inputs = [format_query_for_embedding(q) for q in qwen]
        else:
            golden_inputs = golden
            qwen_inputs = qwen

        golden_resp = await client.embeddings.create(input=golden_inputs, model=model)
        qwen_resp = await client.embeddings.create(input=qwen_inputs, model=model)

        golden_embs = np.array([e.embedding for e in golden_resp.data], dtype=np.float32)
        qwen_embs = np.array([e.embedding for e in qwen_resp.data], dtype=np.float32)

        # Normalize and compute cosine matrix.
        golden_embs /= np.linalg.norm(golden_embs, axis=1, keepdims=True)
        qwen_embs /= np.linalg.norm(qwen_embs, axis=1, keepdims=True)
        sim = golden_embs @ qwen_embs.T  # shape: (L, Q)

        # Greedy 1-to-1 from the label side.
        consumed: set[int] = set()
        matches: list[dict[str, Any]] = []
        missed: list[dict[str, Any]] = []

        for i in range(L):
            available = [j for j in range(Q) if j not in consumed]
            if not available:
                missed.append({"label": golden[i], "best_cos": None})
                continue
            best_j = max(available, key=lambda j: float(sim[i, j]))
            best_cos = float(sim[i, best_j])
            if best_cos >= self.threshold:
                consumed.add(best_j)
                matches.append({"label": golden[i], "query": qwen[best_j], "cos": best_cos})
            else:
                missed.append({"label": golden[i], "best_cos": best_cos})

        K = len(matches)
        unmatched_qwen = [qwen[j] for j in range(Q) if j not in consumed]
        precision = K / Q
        recall = K / L
        f1 = 2 * K / (L + Q)
        return self._emit(
            ctx,
            L,
            Q,
            K,
            matches,
            missed,
            unmatched_qwen,
            precision=precision,
            recall=recall,
            f1=f1,
        )

    def _emit(
        self,
        ctx: EvaluatorContext[str, list[str]],
        L: int,
        Q: int,
        K: int,
        matches: list[dict[str, Any]],
        missed: list[dict[str, Any]],
        unmatched_qwen: list[str],
        *,
        precision: float,
        recall: float,
        f1: float,
    ) -> dict[str, int | float]:
        """Log the case detail to Logfire and return the score dict."""
        logfire.info(
            "memories_eval_case",
            case_name=ctx.name,
            threshold=self.threshold,
            L=L,
            Q=Q,
            matches=K,
            missed_labels=L - K,
            false_positives=Q - K,
            precision=precision,
            recall=recall,
            f1=f1,
            match_detail=matches,
            missed_detail=missed,
            unmatched_qwen=unmatched_qwen,
        )
        return {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "matches": K,
            "missed": L - K,
            "false_positives": Q - K,
            "L": L,
            "Q": Q,
        }


@dataclass
class MicroAveragedPRF1(ReportEvaluator[Any, Any, Any]):
    """Compute micro-averaged precision/recall/F1 across all cases in a report.

    Sums K (matches), L (labels), Q (queries) across the entire report,
    then computes one P, R, F1 from the totals. This is the canonical
    headline metric for variable-cardinality multi-label extraction: each
    prediction counts equally regardless of which case it came from, and
    L=0 cases just contribute 0 to the sums without breaking anything.

    Reads per-case K/L/Q from CosineMatchEvaluator's score dict (keys
    `matches`, `L`, `Q` by default). Cases missing any of those scores
    are skipped silently.
    """

    matches_key: str = "matches"
    labels_key: str = "L"
    queries_key: str = "Q"
    title_prefix: str = "Micro"

    def evaluate(self, ctx: ReportEvaluatorContext[Any, Any, Any]) -> list[ReportAnalysis]:
        """Sum K/L/Q across cases, compute micro P/R/F1, return as ScalarResults."""
        total_k = 0
        total_l = 0
        total_q = 0
        for case in ctx.report.cases:
            k_result = case.scores.get(self.matches_key)
            l_result = case.scores.get(self.labels_key)
            q_result = case.scores.get(self.queries_key)
            if k_result is None or l_result is None or q_result is None:
                continue
            total_k += int(k_result.value)
            total_l += int(l_result.value)
            total_q += int(q_result.value)

        precision = total_k / total_q if total_q > 0 else 0.0
        recall = total_k / total_l if total_l > 0 else 0.0
        denom = total_l + total_q
        f1 = 2 * total_k / denom if denom > 0 else 0.0

        return [
            ScalarResult(title=f"{self.title_prefix} precision", value=precision),
            ScalarResult(title=f"{self.title_prefix} recall", value=recall),
            ScalarResult(title=f"{self.title_prefix} F1", value=f1),
            ScalarResult(title="Total matches", value=total_k),
            ScalarResult(title="Total labels", value=total_l),
            ScalarResult(title="Total queries", value=total_q),
        ]
