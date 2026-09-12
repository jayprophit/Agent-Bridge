"""Context budgeting (v0.3). Deterministic char-based approximation.

Tracks system instructions, task, memory, tool results, file excerpts and
review data. When the budget is approached: compact memory, then truncate
oldest tool results safely (middle-out; paths and errors are never cut in
ways that change meaning). No tokenizer dependency.
"""
from __future__ import annotations

from typing import Any


def approx_size(obj: Any) -> int:
    import json as _j
    try:
        return len(_j.dumps(obj, default=str))
    except (TypeError, ValueError):
        return len(str(obj))


def truncate_middle(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    if limit < 60:
        return text[:limit]
    head = limit * 2 // 3
    tail = limit - head - 30
    return text[:head] + f"\n...[truncated {len(text) - limit} chars]...\n" + text[-tail:]


class ContextBudget:
    def __init__(self, budget_chars: int = 12000, keep_recent_results: int = 6):
        self.budget = budget_chars
        self.keep_recent = keep_recent_results

    def measure(self, parts: dict[str, Any]) -> dict[str, int]:
        sizes = {k: approx_size(v) for k, v in parts.items()}
        sizes["total"] = sum(sizes.values())
        return sizes

    def over(self, parts: dict[str, Any]) -> bool:
        return self.measure(parts)["total"] > self.budget

    def fit_results(self, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Keep the most recent results whole-ish; truncate older ones."""
        if len(results) <= self.keep_recent:
            return results
        cut = len(results) - self.keep_recent
        fitted: list[dict[str, Any]] = []
        for i, r in enumerate(results):
            if i < cut:
                slim = dict(r)
                for k in ("content", "stdout", "stderr", "diff"):
                    if isinstance(slim.get(k), str):
                        slim[k] = truncate_middle(slim[k], 400)
                slim["truncated_for_budget"] = True
                fitted.append(slim)
            else:
                fitted.append(r)
        return fitted
