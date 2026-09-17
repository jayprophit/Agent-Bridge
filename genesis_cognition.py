"""Genesis cognition layer: thinking that produces structured plans.

Genesis THINKS/UNDERSTANDS/REMEMBERS/PLANS/DECIDES/LEARNS/RE-EVALUATES.
This module is the Python-side cognition function that the GenesisAdapter
calls to propose plans. It analyses context, consults ProblemMemory for
historical patterns, and produces plan fields that the execution contract
enforces through its lifecycle.

Cognition owns the PLAN content; the contract owns the PLAN enforcement.
Same boundary as the C++ Genesis cognition modules (capability, affect,
continuity, workspace, world_model).

Design:
  - think(task_id, context) -> dict  (FULL or LIGHTWEIGHT fields)
  - Uses ProblemMemory for recall of similar past failures/workarounds
  - Adaptive depth: small tasks get LIGHTWEIGHT, substantive tasks get FULL
  - Never bypasses the contract; only proposes plans for it to enforce
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from execution_contract import FULL, FULL_FIELDS, LIGHTWEIGHT, LIGHTWEIGHT_FIELDS


@dataclass
class CognitionMemory:
    """Read-only view into ProblemMemory for cognition recall."""
    problems: list[dict[str, Any]] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)


class GenesisCognition:
    """Concrete cognition function for Genesis.

    Produces plan fields by analysing task context and consulting
    historical problem memory. The adapter calls think(); the contract
    enforces the resulting plan through its lifecycle.
    """

    def __init__(self, problem_memory: Any | None = None):
        self._problem_memory = problem_memory
        self._thought_count = 0

    def think(self, task_id: str, context: dict[str, Any]) -> dict[str, Any]:
        """Analyse context and produce plan fields.

        Returns a dict matching either FULL_FIELDS or LIGHTWEIGHT_FIELDS
        depending on task complexity. Includes ``_genesis_depth`` key so
        the adapter can pass the correct depth to the contract.
        """
        self._thought_count += 1
        goal = str(context.get("goal", context.get("objective", "")))
        current_state = str(context.get("current_state", ""))
        constraints = str(context.get("constraints", ""))
        dependencies = str(context.get("dependencies", ""))

        historical = self._recall(goal, context)

        depth = self._assess_depth(goal, context)
        if depth == LIGHTWEIGHT:
            fields = self._lightweight_plan(task_id, goal, context, historical)
        else:
            fields = self._full_plan(task_id, goal, context, historical)
        fields["_genesis_depth"] = depth
        return fields

    def _assess_depth(self, goal: str, context: dict[str, Any]) -> str:
        """Decide LIGHTWEIGHT vs FULL based on goal complexity."""
        goal_len = len(goal)
        has_explicit_state = bool(context.get("current_state"))
        has_constraints = bool(context.get("constraints"))
        has_dependencies = bool(context.get("dependencies"))

        complexity_score = 0
        if goal_len > 120:
            complexity_score += 2
        elif goal_len > 60:
            complexity_score += 1
        if has_explicit_state:
            complexity_score += 1
        if has_constraints:
            complexity_score += 1
        if has_dependencies:
            complexity_score += 1

        return FULL if complexity_score >= 2 else LIGHTWEIGHT

    def _recall(self, goal: str, context: dict[str, Any]) -> CognitionMemory:
        """Consult ProblemMemory for relevant historical patterns."""
        if self._problem_memory is None:
            return CognitionMemory()

        error_hint = str(context.get("error_hint", ""))
        project = str(context.get("project", ""))

        try:
            records = self._problem_memory.query(
                project=project, error_contains=error_hint)
        except Exception:
            return CognitionMemory()

        problems = []
        for r in records[:5]:
            problems.append({
                "problem_id": getattr(r, "problem_id", ""),
                "error": getattr(r, "error", "")[:200],
                "workaround": getattr(r, "workaround", "")[:200],
                "model": getattr(r, "model", ""),
            })

        patterns = []
        if problems:
            unique_workarounds = list({
                p["workaround"] for p in problems if p["workaround"]
            })[:3]
            patterns = unique_workarounds

        return CognitionMemory(problems=problems, patterns=patterns)

    def _lightweight_plan(self, task_id: str, goal: str,
                          context: dict[str, Any],
                          memory: CognitionMemory) -> dict[str, Any]:
        """Produce LIGHTWEIGHT plan fields for small/bounded tasks."""
        change = str(context.get("change", goal))
        expected = str(context.get("expected_result",
                                   context.get("goal", "task complete")))
        verify = str(context.get("verify",
                                  "verify output matches expected result"))

        if memory.patterns:
            verify += (" | historical patterns: " +
                       "; ".join(memory.patterns[:2]))

        return {
            "objective": goal or "complete bounded task",
            "change": change,
            "expected_result": expected,
            "verify": verify,
        }

    def _full_plan(self, task_id: str, goal: str,
                   context: dict[str, Any],
                   memory: CognitionMemory) -> dict[str, Any]:
        """Produce FULL plan fields for substantive tasks."""
        current_state = str(context.get("current_state", "initial state"))
        requirements = str(context.get("requirements", goal))
        constraints = str(context.get("constraints", "none specified"))
        dependencies = str(context.get("dependencies", "none specified"))

        risks = self._assess_risks(goal, context, memory)
        unknowns = self._assess_unknowns(goal, context, memory)
        steps = self._derive_steps(goal, context, memory)
        evidence_requirements = self._evidence_for(goal, context)
        acceptance = self._acceptance_criteria(goal, context)

        return {
            "objective": goal or "complete substantive task",
            "current_state": current_state,
            "requirements": requirements,
            "constraints": constraints,
            "dependencies": dependencies,
            "risks": risks,
            "unknowns": unknowns,
            "steps": steps,
            "evidence_requirements": evidence_requirements,
            "acceptance": acceptance,
        }

    def _assess_risks(self, goal: str, context: dict[str, Any],
                      memory: CognitionMemory) -> str:
        risks = []
        if memory.problems:
            risks.append(
                f"historical failures: {len(memory.problems)} related records")
        if not context.get("current_state"):
            risks.append("no current state provided")
        if not context.get("constraints"):
            risks.append("constraints not explicitly defined")
        return "; ".join(risks) if risks else "low risk"

    def _assess_unknowns(self, goal: str, context: dict[str, Any],
                         memory: CognitionMemory) -> str:
        unknowns = []
        if not context.get("dependencies"):
            unknowns.append("dependencies unknown")
        if memory.problems and not memory.patterns:
            unknowns.append("past failures exist but no workaround patterns")
        return "; ".join(unknowns) if unknowns else "none identified"

    def _derive_steps(self, goal: str, context: dict[str, Any],
                      memory: CognitionMemory) -> str:
        steps = ["analyse context and requirements"]
        if memory.patterns:
            steps.append("apply proven workaround patterns")
        steps.append("execute bounded units under contract")
        steps.append("verify each unit against evidence requirements")
        steps.append("reevaluate and adapt if verification fails")
        return " -> ".join(steps)

    def _evidence_for(self, goal: str, context: dict[str, Any]) -> str:
        evidence = []
        if context.get("verify"):
            evidence.append(f"verification: {context['verify']}")
        evidence.append("contract lifecycle state transitions")
        evidence.append("unit test results")
        return "; ".join(evidence)

    def _acceptance_criteria(self, goal: str, context: dict[str, Any]) -> str:
        criteria = []
        expected = context.get("expected_result")
        if expected:
            criteria.append(f"expected result achieved: {expected}")
        criteria.append("all contract verification steps pass")
        criteria.append("reevaluation confirms completion")
        return "; ".join(criteria) if criteria else "task verified and reevaluated"

    @property
    def thought_count(self) -> int:
        return self._thought_count
