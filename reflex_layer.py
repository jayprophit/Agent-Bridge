"""Reflex execution + task triage (v0.9.0 continuous build).

FAST WHEN THE ANSWER IS EASY. THINK WHEN THINKING IS REQUIRED.

Every request triages first:
  EXECUTE_INLINE_NOW | EXECUTE_REFLEX | EXECUTE_QUICK_AI |
  EXECUTE_DELIBERATIVE_AI | DELEGATE_SPECIALIST | PARALLEL_DELEGATE |
  QUEUE_BACKGROUND | QUEUE_AFTER_DEPENDENCY | ROUTE_REMOTE |
  REQUEST_APPROVAL | REJECT_UNSUPPORTED.

Deterministic work (math, lookups, search, calc, regex, file existence)
routes to engines, never to an LLM. Latency budgets are measured
statistics, never invented guarantees. Additive only; no side effects.
"""
from __future__ import annotations

import ast
import operator
import re
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable


class Route(str, Enum):
    EXECUTE_INLINE_NOW = "EXECUTE_INLINE_NOW"
    EXECUTE_REFLEX = "EXECUTE_REFLEX"
    EXECUTE_QUICK_AI = "EXECUTE_QUICK_AI"
    EXECUTE_DELIBERATIVE_AI = "EXECUTE_DELIBERATIVE_AI"
    DELEGATE_SPECIALIST = "DELEGATE_SPECIALIST"
    PARALLEL_DELEGATE = "PARALLEL_DELEGATE"
    QUEUE_BACKGROUND = "QUEUE_BACKGROUND"
    QUEUE_AFTER_DEPENDENCY = "QUEUE_AFTER_DEPENDENCY"
    ROUTE_REMOTE = "ROUTE_REMOTE"
    REQUEST_APPROVAL = "REQUEST_APPROVAL"
    REJECT_UNSUPPORTED = "REJECT_UNSUPPORTED"


class LatencyBudget(str, Enum):
    REFLEX = "REFLEX"
    INTERACTIVE = "INTERACTIVE"
    NORMAL = "NORMAL"
    BACKGROUND = "BACKGROUND"
    BATCH = "BATCH"


# Patterns that are always deterministic (no model needed).
REFLEX_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"^\s*[\d\s+\-*/().%^]+\s*$", "arithmetic"),
    (r"(?i)\b(convert|how many|to|in)\b.*\d", "unit-conversion"),
    (r"(?i)^(hash|md5|sha)\b", "hash"),
    (r"(?i)\b(file exists|does .* exist)\b", "file-exists"),
    (r"(?i)\b(sort|filter|total|sum|average)\b", "data-op"),
)


def _safe_eval_arith(expr: str) -> Any:
    """Evaluate pure arithmetic only (no names, no calls, no attributes)."""
    tree = ast.parse(expr, mode="eval")
    allowed = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant,
               ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow,
               ast.USub, ast.UAdd, ast.FloorDiv)
    for node in ast.walk(tree):
        if not isinstance(node, allowed):
            raise ValueError("not pure arithmetic")
        if isinstance(node, ast.Constant) and not isinstance(
                node.value, (int, float)):
            raise ValueError("not pure arithmetic")
    ops = {ast.Add: operator.add, ast.Sub: operator.sub,
           ast.Mult: operator.mul, ast.Div: operator.truediv,
           ast.Mod: operator.mod, ast.Pow: operator.pow,
           ast.FloorDiv: operator.floordiv}

    def run(n):
        if isinstance(n, ast.Expression):
            return run(n.body)
        if isinstance(n, ast.Constant):
            return n.value
        if isinstance(n, ast.BinOp):
            return ops[type(n.op)](run(n.left), run(n.right))
        if isinstance(n, ast.UnaryOp):
            return run(n.operand) if isinstance(n.op, ast.UAdd) else -run(n.operand)
        raise ValueError("not pure arithmetic")

    return run(tree)


class ReflexExecutionLayer:
    """Deterministic engines behind one fast interface."""

    def __init__(self):
        self.engines: dict[str, Callable[[str], Any]] = {
            "arithmetic": lambda q: _safe_eval_arith(q.strip()),
            "file-exists": self._file_exists,
        }

    @staticmethod
    def _file_exists(question: str) -> Any:
        m = re.search(r"[A-Za-z]:[\\/][\w\-.:\\/ ]+|\/[\w\-./ ]+", question)
        if not m:
            raise ValueError("no path found")
        import os
        return os.path.exists(m.group(0).strip())

    def can_handle(self, question: str) -> str:
        for pattern, engine in REFLEX_PATTERNS:
            if re.search(pattern, question or ""):
                if engine in self.engines:
                    return engine
        return ""

    def execute(self, question: str) -> dict[str, Any]:
        t0 = time.monotonic()
        engine = self.can_handle(question)
        if not engine:
            return {"ok": False, "engine": "", "error": "not deterministic"}
        try:
            result = self.engines[engine](question)
        except Exception as e:  # noqa: BLE001 - report, don't raise
            return {"ok": False, "engine": engine, "error": str(e)[:200]}
        return {"ok": True, "engine": engine, "result": result,
                "latency_s": round(time.monotonic() - t0, 4)}


@dataclass
class TriageResult:
    route: Route = Route.EXECUTE_DELIBERATIVE_AI
    reason: str = ""
    budget: LatencyBudget = LatencyBudget.NORMAL
    specialist: str = ""
    needs_approval: bool = False


DESTRUCTIVE_HINTS = ("format", "delete partition", "flash", "firmware",
                     "erase", "mkfs", "diskpart clean")


class TaskTriageEngine:
    """Classify first; cheapest sufficient path wins."""

    def __init__(self, reflex: ReflexExecutionLayer | None = None):
        self.reflex = reflex or ReflexExecutionLayer()

    def triage(self, request: str, context: dict[str, Any] | None = None
               ) -> TriageResult:
        context = context or {}
        text = (request or "").lower()
        if any(h in text for h in DESTRUCTIVE_HINTS):
            return TriageResult(Route.REQUEST_APPROVAL,
                                "destructive/high-risk action",
                                LatencyBudget.INTERACTIVE, needs_approval=True)
        if self.reflex.can_handle(request):
            budget = LatencyBudget.REFLEX
            return TriageResult(Route.EXECUTE_INLINE_NOW, "deterministic reflex",
                                budget)
        if context.get("depends_on"):
            return TriageResult(Route.QUEUE_AFTER_DEPENDENCY,
                                "has unfinished dependencies", LatencyBudget.NORMAL)
        if context.get("long_running"):
            return TriageResult(Route.QUEUE_BACKGROUND, "long workload",
                                LatencyBudget.BACKGROUND)
        if context.get("parallel_subtasks"):
            return TriageResult(Route.PARALLEL_DELEGATE, "independent subtasks",
                                LatencyBudget.NORMAL)
        if context.get("specialist"):
            return TriageResult(Route.DELEGATE_SPECIALIST,
                                f"specialist: {context['specialist']}",
                                LatencyBudget.NORMAL,
                                specialist=str(context["specialist"]))
        if context.get("remote_only"):
            return TriageResult(Route.ROUTE_REMOTE, "local unsuitable",
                                LatencyBudget.NORMAL)
        deliberative_hints = ("design", "architect", "strategy", "trade-off",
                                "tradeoff", "compare", "evaluate", "plan the")
        if any(h in text for h in deliberative_hints) or \
                context.get("needs_reasoning"):
            return TriageResult(Route.EXECUTE_DELIBERATIVE_AI,
                                "design/reasoning task", LatencyBudget.NORMAL)
        if len(request.split()) < 40:
            return TriageResult(Route.EXECUTE_QUICK_AI, "short factual task",
                                LatencyBudget.INTERACTIVE)
        return TriageResult(Route.EXECUTE_DELIBERATIVE_AI, "default deep path",
                            LatencyBudget.NORMAL)


class LatencyStats:
    """Measured routing statistics (evidence, not guarantees)."""

    def __init__(self):
        self.samples: dict[str, list[float]] = {}

    def record(self, route: str, latency_s: float) -> None:
        self.samples.setdefault(route, []).append(latency_s)

    def summary(self) -> dict[str, Any]:
        out = {}
        for route, vals in self.samples.items():
            vals = sorted(vals)
            out[route] = {"n": len(vals), "p50": vals[len(vals) // 2],
                          "max": vals[-1]}
        return out

    def to_dict(self) -> dict[str, Any]:
        return {"samples": {k: len(v) for k, v in self.samples.items()},
                "summary": self.summary()}
